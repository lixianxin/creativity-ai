# -*- coding: utf-8 -*-
"""Phase 7-5 V2 Runtime 离线烟囱测试（不触网、不花 API）。

覆盖迁移表要求的三类失败路径优先测试：
① Agent 坏结构：ResultValidator 拒绝/返工/红线系统规则/结论程序归一；
② 错误分类：normalize_llm_error 8 类归一 + RetryPolicy 差异化策略；
③ 中断恢复：RunStore checkpoint / orphan 接管 / 终态保护 / resume 全链路。

运行：python tests/system/test_v2_runtime.py
"""
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.base_agent import BaseAgent
from agents.registry import registry, AgentSpec
from core.llm_errors import (
    normalize_llm_error, RetryPolicy, LLMErrorKind, LLMRequestError,
)
from core.result_validator import (
    validate_result, REDLINE_FORCED_CONCLUSION,
)
from core.run import (
    RUN_RUNNING, RUN_SUCCESS, RUN_PAUSED,
    AGENT_RUNNING, AGENT_SUCCESS, AGENT_QUEUED, AGENT_PAUSED,
)
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline
from schemas.agent_result import AgentResult, STATUS_SUCCESS, STATUS_FAILED

_PASSED = 0
_FAILED = 0


def check(name: str, passed: bool, detail: str = ""):
    global _PASSED, _FAILED
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    if passed:
        _PASSED += 1
    else:
        _FAILED += 1
    return passed


# ───────────────────────── 合格样本（12 Agent 最小合格报告） ─────────────────────────

_PAD = ("以上判断基于当前提交的有限信息，后续应通过真实用户接触与小范围实验继续修正。"
        "团队需要保留判断被推翻的可能性，并在下一阶段补充更有力的行为证据。"
        "任何单一信息来源都不足以支撑最终决策，交叉验证与持续跟进应贯穿项目验证的全过程。")

GOOD_TEXTS = {
    "user_insight":
        "目标用户的核心痛点明确，需求强度需要通过真实访谈与行为观察验证。当前证据等级偏低，"
        "用户口头表达的兴趣不能算作付费证据。使用者是学生，但付费方可能是学校机构，二者存在分离风险。"
        "应区分用户自述需求与高频真实痛点，并标注哪些结论待验证。" + _PAD,
    "market_analysis":
        "市场规模按 TAM、SAM、SOM 三层展开。TAM 约 300 亿元（行业报告估算，待验证），"
        "SAM 约 60 亿元（目标高校场景测算），SOM 约 6 亿元（保守假设，三年目标）。"
        "每层数字均为估算口径，来源为公开统计与参数推算，不是精确数据，必须标注待验证。"
        "市场增长趋势受政策与预算周期影响，存在不确定性。" + _PAD,
    "competitor_analysis":
        "竞品按三分法梳理：直接竞品为同类 AI 评审工具，间接竞品为人工咨询与创业课程，"
        "替代方案包括学校老师免费指导与免费模板。直接竞品之间同质化明显，差异化必须落在角色冲突与红线机制上。"
        "去中介化威胁较低，但免费替代会压制付费意愿。团队需要证明自身壁垒与护城河不只是提示词工程。" + _PAD,
    "product_design":
        "产品应以 MVP 为核心，最小版本只保留项目输入到终审报告的闭环，核心任务是让风险被看见。"
        "功能砍减应优先砍掉知识库管理与多模板，避免冗余功能稀释核心任务。"
        "人工 MVP 可以先验证学校客户是否愿意为审查结果付费，产品闭环成立后再考虑协作功能。" + _PAD,
    "business_model":
        "价值交换逻辑是学校为评审能力付费，学生免费使用。付费方为创业学院或教务处，"
        "收入来源是年度机构采购，成本主要是模型 API 与运维。当前断点在于免费学生用户不直接产生收入，"
        "付费方的采购预算周期长。需要验证付费方是否认可报告价值，收入与成本都还缺少真实订单证据。" + _PAD,
    "finance":
        "财务测算的关键变量包括客单价、收入、成本、利润、LTV 与 CAC。当前所有数字都只能在显式假设下推算："
        "假设单校年费 5 万元、假设年签约 20 所学校，收入约 100 万元；API 成本与交付成本未核实，利润无法可靠计算。"
        "LTV/CAC 缺少留存与获客数据支撑。结论：现阶段财务无法可靠计算。" + _PAD,
    "growth_ops":
        "增长飞轮目前不清晰，AARRR 各环节中激活与留存缺乏定义。冷启动应从 2-3 所种子学校的渠道切入，"
        "通过老师背书获客，再向同类院校复制。渠道有效性待验证，没有自然传播机制时飞轮无法自转。"
        "需要先定义激活行为，再验证留存，最后才是扩大获客投入。" + _PAD,
    "risk_review":
        "六类风险排查：合规与法律方面，生成式 AI 服务可能需要备案与算法许可，进校园还存在准入资质要求；"
        "数据与隐私方面，学生提交的项目信息涉及个人信息保护，需告知同意与最小必要；"
        "内容与安全方面，AI 评审结论需要内容审核机制，避免误导性建议；"
        "系统与运营方面，依赖单一模型 API 构成单点风险；伦理与社会方面，评审结论可能影响学生公平，需保留人工申诉；"
        "落地与资质方面，经营主体与 ICP 资质须前置。未发现致命风险。" + _PAD,
    "red_team":
        "五维假设攻击：需求假设上，老师口头感兴趣不代表学生有真痛点，伪需求风险高，证据是什么；"
        "付费假设上，感兴趣的老师与掏钱的采购方不是同一人，付费意愿没有证据；"
        "竞争假设上，免费的老师指导与现成模板是替代方案，为什么不用现成的；"
        "增长假设上，渠道从哪来、冷启动凭什么跑通均无证据；"
        "壁垒假设上，巨头进校产品一旦跟进，提示词层护城河很弱。每个攻击点都给出证伪条件：真实订单、复购行为、留存数据方可推翻。" + _PAD,
    "commander":
        "项目阶段判断为想法验证阶段，尚未进入产品验证。核心矛盾是学校口头兴趣与真实采购之间的证据鸿沟。\n"
        "行动项：\n"
        "1. 两周内完成 10 位创业学院老师付费意向访谈；\n"
        "2. 用人工 MVP 交付 1 次完整评审验证付费意愿；\n"
        "3. 明确红线风险清单并确认备案路径。\n"
        "优先做证据补全，不要先扩功能。" + _PAD,
    "project_review":
        "五维终审评分：用户与需求 2 分，仅有口头兴趣无行为证据；市场与竞争 3 分，市场存在但同质化竞争明显；"
        "产品与方案 3 分，MVP 闭环基本成立但需砍减；商业与财务 2 分，财务无法可靠计算；"
        "风险与合规 2 分，备案与准入资质未落实。冲突终裁以风险与合规的保守判断为准。"
        "终审结论：有条件准入路演，前提是补齐合规路径与付费证据。" + _PAD,
    "pitch_defense":
        "模拟评委追问：客户为什么现在掏钱、备案没下来怎么办、巨头跟进怎么办，三个问题目前都缺少有力回答，"
        "部分环节存在被击穿风险。手牌亮点是红线一票否决的系统设计，属于可防御的差异化。"
        "结论：可以路演，答辩时必须主动承认未验证项，避免被评委追问击穿。" + _PAD,
}

MARKET_BAD = "市场分析：TAM 约 300 亿元。市场在增长，值得关注。"

RED_CONFLICT_TEXT = (
    "五维终审评分：用户与需求 2 分，仅有口头兴趣无行为证据；市场与竞争 3 分，市场存在但同质化竞争明显；"
    "产品与方案 3 分，MVP 闭环基本成立；商业与财务 2 分，财务无法可靠计算；"
    "风险与合规 1 分，备案与准入资质均未落实，材料存在重大缺口。"
    "各维度评分依据前置报告的证据强度给出，证据不足的维度按最低分处理，委员会需要对结论承担责任。"
    "本项目命中红线，一票否决，风险等级为最高。终审结论：准入路演。"
)


def _result(name, raw):
    return AgentResult(agent_name=name, status=STATUS_SUCCESS, summary=raw[:80],
                       raw_output=raw, metadata={"chars": len(raw)})


# ───────────────────────── ① 坏结构 / 校验闸门 ─────────────────────────

def test_validator_good_texts():
    print("\n【1】12 Agent 合格样本全部通过校验")
    for name, text in GOOD_TEXTS.items():
        vr = validate_result(_result(name, text))
        check(f"{name} 合格样本 accepted", vr.accepted,
              "; ".join(i.code for i in vr.errors) or "无 error")


def test_validator_bad_structures():
    print("\n【2】坏结构必须被拒绝（error）")
    cases = [
        ("empty", "user_insight", "", "EMPTY_OUTPUT"),
        ("too_short", "user_insight", "太短了", "OUTPUT_TOO_SHORT"),
        ("refusal", "user_insight",
         "很抱歉，作为一个人工智能语言模型，我无法访问互联网，因此不能提供该分析。" + "补充内容" * 60,
         "REFUSAL_DETECTED"),
        ("market_missing_tiers", "market_analysis",
         "市场分析：TAM 约 300 亿元。" + "市场持续扩大，政策利好。" * 30, "MARKET_MISSING_TIERS"),
        ("redteam_dimensions", "red_team",
         "只攻击需求假设：用户可能没有真痛点，证据不足。" + "其余问题暂不展开讨论。" * 30,
         "REDTEAM_MISSING_DIMENSIONS"),
        ("review_dimensions", "project_review",
         "只评用户与需求 2 分，其他维度略过。" + "继续补充文字内容到足够长度。" * 30,
         "REVIEW_MISSING_DIMENSIONS"),
    ]
    for label, name, text, expect_code in cases:
        vr = validate_result(_result(name, text))
        codes = [i.code for i in vr.errors]
        check(f"{label} 被拒绝（{expect_code}）", (not vr.accepted) and expect_code in codes,
              f"errors={codes}")


def test_validator_warnings():
    print("\n【3】软问题给 warning 但仍接受")
    # 市场报告数字无来源
    raw = ("市场 TAM/SAM/SOM 分别为 300 亿元、60 亿元、6 亿元，增长率 25%。"
           "行业前景广阔，团队判断机会明确，赛道具备长期吸引力，"
           "参与者持续增多，政策导向保持鼓励，资本关注度逐年升温，"
           "从业者普遍看好未来空间，创业公司活跃度维持高位。" + _PAD)
    vr = validate_result(_result("market_analysis", raw))
    check("无来源数字产生 warning 且 accepted",
          vr.accepted and any(i.code == "MARKET_UNSOURCED_NUMBERS" for i in vr.warnings))


def test_system_signals():
    print("\n【4】红线/阻断/结论由程序归一（系统规则）")
    # 风险官：程序判定 blocking
    vr = validate_result(_result("risk_review", "该项目未备案即上线属于致命风险，做了即违法，必须先取得许可。" + _PAD * 2))
    check("risk blocking 程序判定为 True", vr.signals.get("blocking") is True)
    vr2 = validate_result(_result("risk_review", GOOD_TEXTS["risk_review"]))
    check("risk 合格样本 blocking=False", vr2.signals.get("blocking") is False)

    # 评审官：红线与准入冲突
    vr3 = validate_result(_result("project_review", RED_CONFLICT_TEXT))
    check("红线冲突判 REDLINE_CONFLICT error",
          any(i.code == "REDLINE_CONFLICT" for i in vr3.errors))
    check("redline_triggered 程序信号=True", vr3.signals.get("redline_triggered") is True)

    # 结论归一
    check("评审结论归一=有条件准入路演",
          validate_result(_result("project_review", GOOD_TEXTS["project_review"])).signals.get("conclusion")
          == "有条件准入路演")
    check("总指挥阶段结论程序提取",
          "想法验证" in str(validate_result(_result("commander", GOOD_TEXTS["commander"])).signals.get("conclusion", "")))
    check("路演结论程序提取",
          validate_result(_result("pitch_defense", GOOD_TEXTS["pitch_defense"])).signals.get("conclusion", "").find("可以路演") >= 0)
    check("财务结论归一=无法可靠计算",
          validate_result(_result("finance", GOOD_TEXTS["finance"])).signals.get("conclusion")
          == "无法可靠计算")
    check("击穿数程序统计>=2",
          validate_result(_result("pitch_defense", GOOD_TEXTS["pitch_defense"])).signals.get("pierced_count", 0) >= 2)


# ───────────────────────── 执行器返工闸门（打桩 LLM） ─────────────────────────

CALLS = {}


class FakeAgent(BaseAgent):
    """不触网的假 Agent：run 返回预置文本；repair 由基类走打桩的 llm.generate。"""

    def __init__(self, name, texts):
        self.prompt_name = name
        super().__init__()
        self._texts = texts

    def run(self, project_input: str, context: dict = None) -> AgentResult:
        CALLS[self.prompt_name] = CALLS.get(self.prompt_name, 0) + 1
        raw = self._texts[self.prompt_name]
        # 模拟真实 run 的副作用：缓存上一次调用上下文，供 repair() 返工使用
        self._last_user_content = project_input
        self._last_max_tokens = 16000
        return self._build_result(summary=raw[:80], raw_output=raw, metadata={"chars": len(raw)})


def _patch_build(texts):
    def fake_build(self):
        return FakeAgent(self.name, texts)
    orig = AgentSpec.build_agent
    AgentSpec.build_agent = fake_build
    return orig


def test_execute_repair_gate():
    print("\n【5】执行器校验闸门：坏结构→返工→接受；红线冲突→系统强制")
    tmp = Path(tempfile.mkdtemp())
    import agents.base_agent as ba
    orig_gen = ba.llm.generate

    # 5a 市场报告缺 SAM/SOM → 返工 1 次后合格
    spec = registry.get("market_analysis")
    orig_build = _patch_build({"market_analysis": MARKET_BAD})
    try:
        ba.llm.generate = lambda *a, **k: GOOD_TEXTS["market_analysis"]
        pipe = CommitteePipeline(report_dir=str(tmp), run_store=RunStore(str(tmp / "t1.db")))
        outcome = pipe._execute_agent(spec, "测试项目", None, run_id=None)
        check("坏市场报告返工后 accepted", outcome.result.status == STATUS_SUCCESS)
        check("repaired 标记落 metadata", outcome.result.metadata.get("repaired") is True)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen

    # 5b 红线冲突返工仍不改 → 程序强制改判
    spec2 = registry.get("project_review")
    orig_build = _patch_build({"project_review": RED_CONFLICT_TEXT})
    try:
        ba.llm.generate = lambda *a, **k: RED_CONFLICT_TEXT
        pipe = CommitteePipeline(report_dir=str(tmp), run_store=RunStore(str(tmp / "t2.db")))
        outcome = pipe._execute_agent(spec2, "测试项目", None, run_id=None)
        check("红线冲突返工后仍被系统接受（强制）", outcome.result.status == STATUS_SUCCESS)
        check("redline_triggered=True", outcome.result.metadata.get("redline_triggered") is True)
        check("系统强制改判结论", outcome.result.conclusion == REDLINE_FORCED_CONCLUSION)
        check("redline_forced_by_system 标记",
              outcome.result.metadata.get("redline_forced_by_system") is True)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


# ───────────────────────── ② LLM 错误归一 ─────────────────────────

class _FakeHTTPError(Exception):
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class _FakeResponse:
    def __init__(self, text, status_code=None):
        self.text = text
        self.status_code = status_code


def test_error_normalization():
    print("\n【6】LLM 错误归一化分类")
    cases = [
        ("auth_401", _FakeHTTPError("Unauthorized", 401), LLMErrorKind.AUTH),
        ("auth_403", _FakeHTTPError("Forbidden", 403), LLMErrorKind.AUTH),
        ("quota_402", _FakeHTTPError("Payment Required", 402), LLMErrorKind.QUOTA),
        ("quota_keyword", Exception("Error: insufficient_quota for this key"), LLMErrorKind.QUOTA),
        ("rate_429", _FakeHTTPError("Too Many Requests", 429), LLMErrorKind.RATE_LIMIT),
        ("rate_keyword", Exception("Requests per minute exceeded"), LLMErrorKind.RATE_LIMIT),
        ("context", Exception("This model's context_length is 65536, prompt is too long"),
         LLMErrorKind.CONTEXT_LIMIT),
        ("output_limit", Exception("max_tokens is too large for this model"),
         LLMErrorKind.OUTPUT_LIMIT),
        ("timeout_httpx", type("E", (Exception,), {"__module__": "httpx"})("read timed out"),
         LLMErrorKind.TIMEOUT),
        ("network", type("E", (Exception,), {"__module__": "httpcore"})("connection refused"),
         LLMErrorKind.NETWORK),
        ("unknown", Exception("weird failure xyz"), LLMErrorKind.UNKNOWN),
    ]
    for label, exc, expect in cases:
        kind = normalize_llm_error(exc).kind
        check(f"{label} → {expect}", kind == expect, f"got {kind}")

    # 混排错误体：余额不足+缩短输入，必须优先归为额度而不是上下文
    mixed = Exception("余额不足，请减少输入过长内容 (context_length)")
    check("混排错误优先归 QUOTA", normalize_llm_error(mixed).kind == LLMErrorKind.QUOTA)

    # 已是归一错误不重复包装
    original = LLMRequestError(LLMErrorKind.AUTH, "x")
    check("归一错误幂等", normalize_llm_error(original) is original)


def test_retry_policy():
    print("\n【7】RetryPolicy 差异化策略")
    p = RetryPolicy()
    check("AUTH 不可重试", not p.can_retry(LLMErrorKind.AUTH, 1))
    check("QUOTA 不可重试", not p.can_retry(LLMErrorKind.QUOTA, 1))
    check("CONTEXT_LIMIT 动作=RAISE", p.action_for(LLMErrorKind.CONTEXT_LIMIT) == "raise")
    check("QUOTA 动作=PAUSE_RUN", p.action_for(LLMErrorKind.QUOTA) == "pause_run")
    check("AUTH 动作=FAIL_RUN", p.action_for(LLMErrorKind.AUTH) == "fail_run")
    check("RATE_LIMIT 可多次重试", p.can_retry(LLMErrorKind.RATE_LIMIT, 1)
          and p.can_retry(LLMErrorKind.RATE_LIMIT, 3))
    check("RATE_LIMIT 退避递增",
          p.backoff_seconds(LLMErrorKind.RATE_LIMIT, 1) < p.backoff_seconds(LLMErrorKind.RATE_LIMIT, 3))
    check("EMPTY_RESPONSE 可重试", p.can_retry(LLMErrorKind.EMPTY_RESPONSE, 1))
    check("超过上限不可重试", not p.can_retry(LLMErrorKind.EMPTY_RESPONSE, 3))


# ───────────────────────── ③ RunStore / 中断恢复 ─────────────────────────

def test_run_store_lifecycle():
    print("\n【8】RunStore：checkpoint / orphan 接管 / 终态保护")
    tmp = Path(tempfile.mkdtemp())
    store = RunStore(str(tmp / "runs.db"))

    run = store.create_run("测试项目", registry.stage_specs_tuples(), report_dir=str(tmp))
    rid = run.run_id
    check("创建 Run 预置 12 个 queued AgentRun",
          len(store.list_agent_runs(rid)) == 12)

    spec = registry.get("user_insight")
    store.start_agent(rid, spec.name)
    check("start 后 Run=running", store.get_run(rid).status == RUN_RUNNING)
    store.finish_agent(rid, spec.name, AGENT_SUCCESS, output_path=str(tmp / "01_user.md"),
                       metadata={"elapsed_s": 3.1}, increment_retry=True)
    ar = next(a for a in store.list_agent_runs(rid) if a.agent_name == spec.name)
    check("AgentRun success + retry_count=1",
          ar.status == AGENT_SUCCESS and ar.retry_count == 1)

    # orphan 接管
    n = store.mark_orphaned_runs_paused()
    check("orphan run 接管为 paused（>=1）", n >= 1
          and store.get_run(rid).status == RUN_PAUSED)
    running_left = [a for a in store.list_agent_runs(rid) if a.status in (AGENT_RUNNING, AGENT_QUEUED)]
    check("未完成 AgentRun 一并 paused", len(running_left) == 0
          and any(a.status == AGENT_PAUSED for a in store.list_agent_runs(rid)))

    # resume：paused/queued/failed 回 queued，success 保持
    store.resume_run(rid)
    after = {a.agent_name: a.status for a in store.list_agent_runs(rid)}
    check("resume 后成功棒保持 success", after["user_insight"] == AGENT_SUCCESS)
    check("resume 后其余棒回 queued",
          all(v == AGENT_QUEUED for k, v in after.items() if k != "user_insight"))

    # 终态保护
    store.finish_run(rid, success_count=12, fail_count=0)
    store.mark_run_running(rid)
    check("终态 Run 不可回写为 running", store.get_run(rid).status == RUN_SUCCESS)
    blocked = False
    try:
        store.resume_run(rid)
    except ValueError:
        blocked = True
    check("success Run 不可 resume", blocked)


def test_resume_from_crash():
    print("\n【9】全链路：崩溃 → orphan 接管 → resume 精确续跑（成功棒不花调用）")
    tmp = Path(tempfile.mkdtemp())
    store = RunStore(str(tmp / "runs.db"))
    pipe = CommitteePipeline(report_dir=str(tmp), run_store=store)

    run = store.create_run("测试创业项目", registry.stage_specs_tuples(), report_dir=str(tmp))
    rid = run.run_id

    # 模拟：前 3 棒已成功（报告文件 + checkpoint），第 4 棒 running 时进程被杀
    agents = store.list_agent_runs(rid)
    for ar in agents[:3]:
        spec = registry.get(ar.agent_name)
        out = tmp / f"{spec.seq}_{spec.stage_key}.md"
        out.write_text(GOOD_TEXTS[spec.name], encoding="utf-8")
        store.start_agent(rid, spec.name)
        store.finish_agent(rid, spec.name, AGENT_SUCCESS, output_path=str(out),
                           metadata={"elapsed_s": 1.0})
    store.start_agent(rid, "product_design")  # 第 4 棒僵在 running

    # 打桩全部 12 Agent（不触网）
    CALLS.clear()
    orig_build = _patch_build(GOOD_TEXTS)
    try:
        ctx = pipe.resume(rid, save=True)
    finally:
        AgentSpec.build_agent = orig_build

    run2 = store.get_run(rid)
    check("resume 后 Run 达终态", run2.status in (RUN_SUCCESS, "completed_with_errors"), run2.status)

    statuses = {a.agent_name: a.status for a in store.list_agent_runs(rid)}
    check("12 棒全部 success", all(v == AGENT_SUCCESS for v in statuses.values()),
          f"{[(k, v) for k, v in statuses.items() if v != AGENT_SUCCESS]}")

    check("已 checkpoint 的前 3 棒零调用",
          all(CALLS.get(name, 0) == 0 for name in
              ["user_insight", "market_analysis", "competitor_analysis"]))
    check("其余 9 棒各执行 1 次",
          all(CALLS.get(registry.all()[i].name, 0) == 1 for i in range(3, 12)))

    check("ctx 恢复+续跑共 12 份报告", len(ctx.reports) == 12)
    check("final_report.md 落盘", (tmp / "final_report.md").exists())
    reviewer = ctx.get_report("project_review")
    check("恢复链路中评审红线信号为程序值", reviewer.metadata.get("redline_triggered") is False)


def test_registry():
    print("\n【10】AgentRegistry：12 棒注册 / DAG 依赖声明 / 并行就绪集")
    check("注册 12 个 Agent", len(registry.all()) == 12)
    # Phase 7-7：风险官进入 DAG 第 0 层独立审查，并行就绪集为 8（7 专家 + 风险官）
    check("第 0 层 8 个无依赖节点可并行", len(registry.parallel_ready()) == 8)
    review_deps = registry.get("project_review").dependencies
    check("评审官硬依赖 commander（+risk/red_team 共 3）",
          "commander" in review_deps and len(review_deps) == 3, str(review_deps))
    check("答辩官硬依赖评审官", "project_review" in registry.get("pitch_defense").dependencies)
    # Phase 7-7：hard/soft 边声明
    check("总指挥硬依赖 risk/red_team，软依赖 7 专家",
          set(registry.get("commander").dependencies) == {"risk_review", "red_team"}
          and len(registry.get("commander").soft_dependencies) == 7)
    check("风险官具备 blocking 能力", "blocking" in registry.get("risk_review").capabilities)
    check("评审官具备 redline_veto 能力", "redline_veto" in registry.get("project_review").capabilities)
    agent = registry.get("finance").build_agent()
    check("build_agent 动态实例化", agent.__class__.__name__ == "FinanceAgent")


def main():
    print("=" * 60)
    print("Phase 7-5 V2 Runtime 离线烟囱测试")
    print("=" * 60)
    tests = [
        test_validator_good_texts,
        test_validator_bad_structures,
        test_validator_warnings,
        test_system_signals,
        test_execute_repair_gate,
        test_error_normalization,
        test_retry_policy,
        test_run_store_lifecycle,
        test_resume_from_crash,
        test_registry,
    ]
    for t in tests:
        try:
            t()
        except Exception:
            global _FAILED
            _FAILED += 1
            print(f"  ❌ {t.__name__} 抛异常：")
            print(traceback.format_exc())

    print("\n" + "=" * 60)
    print(f"结果：{_PASSED} 通过 / {_FAILED} 失败")
    print("=" * 60)
    sys.exit(1 if _FAILED else 0)


if __name__ == "__main__":
    main()
