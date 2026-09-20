# -*- coding: utf-8 -*-
"""Phase 7-6 故障注入 / 恢复 / 一致性 离线验收（不触网、不花 API）。

与 test_v2_runtime.py（单元级烟囱）互补，本脚本按"验收标准"组织，全部走真实生产
代码路径（LLMClient.generate / CommitteePipeline.run / resume / RunStore），
仅在边界上打桩：LLM HTTP 传输、Agent 产出。

验收映射：
  验收1 ResultValidator/Repair ……………… A 组（脏数据不得以 success 入下游）
  验收2 LLM Error 差异化策略 ………………… B 组（真实 openai 异常对象注入到 generate）
  验收3 Checkpoint/Resume …………………… C 组（第4棒后 kill -9 语义，新实例接管）
  验收4 Failure Isolation …………………… D 组（单棒失败不连坐，下游降级继续）
  验收5 Redline/Conclusion 一致性 ………… E 组（跨层程序检查 + 红线强制改判）
真实 12 Agent / Final Report / UI 三项由 phase_7_6_real_run.py 与浏览器验收。

运行：python tests/system/test_phase_7_6_acceptance.py
"""
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
import openai

import agents.base_agent as ba
import core.llm_client as lc
from agents.registry import registry, AgentSpec
from core.llm_errors import LLMErrorKind, LLMRequestError
from core.result_validator import cross_check_decisions, REDLINE_FORCED_CONCLUSION
from core.run import RUN_SUCCESS, RUN_PAUSED, RUN_FAILED, RUN_COMPLETED_WITH_ERRORS
from core.run_store import RunStore
from pipeline.orchestrator import CommitteePipeline
from schemas.agent_result import AgentResult, STATUS_SUCCESS, STATUS_FAILED

import test_v2_runtime as tv
from test_v2_runtime import GOOD_TEXTS, MARKET_BAD, RED_CONFLICT_TEXT

_PASSED = 0
_FAILED = 0


def check(name, passed, detail=""):
    global _PASSED, _FAILED
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    if passed:
        _PASSED += 1
    else:
        _FAILED += 1


INPUT = "创想∞ AI创业委员会：面向高校创新创业场景的 AI 评审系统。"

# 竞品官的永久坏输出（短 → 必被 OUTPUT_TOO_SHORT 拒绝）
BAD_COMPETITOR = "竞品分析：市场上竞品很少，我们差异明显，暂时没有对手。"

SPY_CONTEXT = {}


# ───────────────────────── Agent 打桩 ─────────────────────────

def install_agents(texts, *, raises=None, first_outputs=None):
    """把 Registry 的 build_agent 换为打桩 Agent。

    raises:       {agent_name: Exception} run() 直接抛（模拟 LLM 服务错误）
    first_outputs:{agent_name: raw}       仅首次 run 用该文本（模拟非法首输出）
    """
    raises = raises or {}
    first_outputs = first_outputs or {}
    first_seen = set()

    def fake_build(self):
        texts_ref = texts

        class ScriptedSpy(tv.FakeAgent):
            def run(self, project_input, context=None):
                SPY_CONTEXT.setdefault(self.prompt_name, []).append(context)
                if self.prompt_name in raises:
                    raise raises[self.prompt_name]
                if self.prompt_name in first_outputs and self.prompt_name not in first_seen:
                    first_seen.add(self.prompt_name)
                    self._texts = {**self._texts, self.prompt_name: first_outputs[self.prompt_name]}
                return super().run(project_input, context)

        return ScriptedSpy(self.name, texts_ref)

    orig = AgentSpec.build_agent
    AgentSpec.build_agent = fake_build
    return orig


# ───────────────────────── LLM HTTP 传输打桩 ─────────────────────────

_REQ = httpx.Request("POST", "https://api.example.com/v1/chat/completions")


def _status_error(code, message, exc_cls):
    resp = httpx.Response(code, request=_REQ, json={"error": {"message": message}})
    return exc_cls(message, response=resp, body={"error": {"message": message}})


class _Msg:
    def __init__(self, content):
        self.content = content
        self.reasoning_content = None


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _Msg(content)
        self.finish_reason = finish_reason


class _Resp:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_Choice(content, finish_reason)]


class _Completions:
    def __init__(self, script):
        self.script = script
        self.calls = []
        self.kwargs = []

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Resp(item[0], item[1])


class _RawClient:
    def __init__(self, script):
        self.chat = types.SimpleNamespace(completions=_Completions(script))


def make_client(script, *, switch_fn=None):
    """构造不走网络的 LLMClient；switch_fn(attempted)->bool 控制平台切换行为。"""
    c = lc.LLMClient()
    raw = _RawClient(script)
    c._client = raw
    c._platform = types.SimpleNamespace(name="deepseek", model="m-test")
    c._raw = raw
    if switch_fn is not None:
        c._switch_platform = lambda attempted: switch_fn(c, attempted)
    else:
        c._switch_platform = lambda attempted: False
    return c


def expect_raise(kind_expected, client):
    try:
        client.generate("sys", "user")
        return None, "未抛出异常"
    except LLMRequestError as e:
        return e, f"kind={e.kind}"
    except Exception as e:  # noqa
        return None, f"抛出非归一异常 {type(e).__name__}: {str(e)[:80]}"


# ════════════════════════ A 组：非法输出拦截 + Repair ════════════════════════

def test_a_validator_repair_gate():
    print("\n【验收1】非法 Agent 输出：拦截 → repair 1 次 → 再校验；脏数据不得以 success 入下游")
    tmp = Path(tempfile.mkdtemp())
    orig_gen = ba.llm.generate

    # A1 极短非法输出 + 返工仍非法 → 该棒 failed
    orig_build = install_agents(GOOD_TEXTS, first_outputs={"market_analysis": "测试"})
    try:
        ba.llm.generate = lambda *a, **k: "测试"
        pipe = CommitteePipeline(report_dir=str(tmp / "a1"), run_store=RunStore(str(tmp / "a1.db")))
        out = pipe._execute_agent(registry.get("market_analysis"), INPUT, None, run_id=None)
        codes = [i.code for i in out.vr.errors]
        check("非法短输出被校验拒绝（OUTPUT_TOO_SHORT）", out.result.status == STATUS_FAILED
              and "OUTPUT_TOO_SHORT" in codes, str(codes))
        check("失败摘要含返工后仍不合格", "返工后仍不合格" in out.result.summary)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen

    # A2 首输出缺 SAM/SOM → 返工合格；下游拿到的是返工后的 success 报告
    SPY_CONTEXT.clear()
    tv.CALLS.clear()
    orig_build = install_agents(GOOD_TEXTS, first_outputs={"market_analysis": MARKET_BAD})
    try:
        ba.llm.generate = lambda *a, **k: GOOD_TEXTS["market_analysis"]
        pipe = CommitteePipeline(report_dir=str(tmp / "a2"), run_store=RunStore(str(tmp / "a2.db")))
        ctx = pipe.run(INPUT)
        rows = {a.agent_name: a for a in pipe.store.list_agent_runs(pipe.current_run_id)}
        m_row = rows["market_analysis"]
        check("市场官返工后 success", m_row.status == "success")
        check("checkpoint 记录 retry_count=1", m_row.retry_count == 1, f"got {m_row.retry_count}")
        market = ctx.get_report("market_analysis")
        check("进入下游的是返工后正文（脏首输出被替换）",
              market.raw_output.strip() == GOOD_TEXTS["market_analysis"].strip()
              and "TAM 约 300 亿元。市场在增长" not in market.raw_output)
        check("metadata.repaired=True", market.metadata.get("repaired") is True)
        # Phase 7-7 图驱动：风险官在第 0 层独立审查（context=None），
        # 红队是第一个消费市场报告的下游（soft 依赖含 market_analysis）。
        downstream = SPY_CONTEXT["red_team"][0]["reports"]
        m_in_ctx = next(r for r in downstream if r.agent_name == "market_analysis")
        check("下游 context 中市场官为 success 且带 repaired 标记",
              m_in_ctx.status == STATUS_SUCCESS and m_in_ctx.metadata.get("repaired") is True)
        check("风险官在第 0 层独立运行（不吃上游 context）",
              SPY_CONTEXT["risk_review"][0] is None)
        check("A2 整 Run 成功（返工挽救，不连坐）", pipe.store.get_run(pipe.current_run_id).status
              == RUN_SUCCESS)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


# ════════════════════════ B 组：LLM 错误差异化策略 ════════════════════════

def test_b_llm_error_strategies():
    print("\n【验收2】LLM 错误注入（真实 openai 异常）→ normalize → 差异化 retry/switch/pause/fail")
    tmp = Path(tempfile.mkdtemp())
    orig_sleep = lc.time.sleep
    lc.time.sleep = lambda *_a, **_k: None
    try:
        # B1 超时 ×2 → 第 3 次成功
        c = make_client([
            openai.APITimeoutError(request=_REQ),
            openai.APITimeoutError(request=_REQ),
            ("正常正文结果", "stop"),
        ])
        assert c.generate("s", "u") == "正常正文结果"
        check("timeout：重试后成功（HTTP 调用 3 次）",
              len(c._raw.chat.completions.kwargs) == 3,
              f"kwargs={len(c._raw.chat.completions.kwargs)}")

        # B2 429 ×1 → 重试成功
        c = make_client([_status_error(429, "rate limit", openai.RateLimitError),
                         ("ok", "stop")])
        check("rate_limit：退避重试后成功", c.generate("s", "u") == "ok"
              and len(c._raw.chat.completions.kwargs) == 2)

        # B3 429 持续 → 第 4 次后放弃（策略上限 4）
        c = make_client([_status_error(429, "rate limit", openai.RateLimitError)] * 6)
        e, detail = expect_raise(LLMErrorKind.RATE_LIMIT, c)
        check("rate_limit 持续：达策略上限后抛出（共 4 次，非无限重试）",
              e is not None and e.kind == LLMErrorKind.RATE_LIMIT and len(c._raw.chat.completions.kwargs) == 4,
              f"{detail}, calls={len(c._raw.chat.completions.kwargs)}")

        # B4 401 → 立即失败 Run，一次都不重试
        c = make_client([_status_error(401, "invalid api key", openai.AuthenticationError)])
        e, detail = expect_raise(LLMErrorKind.AUTH, c)
        check("auth：立即抛出、零重试（HTTP 调用 1 次）",
              e is not None and e.kind == LLMErrorKind.AUTH and len(c._raw.chat.completions.kwargs) == 1,
              detail)

        # B5 402/额度 → 立即暂停语义、零重试
        c = make_client([_status_error(402, "insufficient_quota", openai.APIStatusError)])
        e, detail = expect_raise(LLMErrorKind.QUOTA, c)
        check("quota：立即抛出（无备用平台时交执行器暂停 Run）",
              e is not None and e.kind == LLMErrorKind.QUOTA and len(c._raw.chat.completions.kwargs) == 1,
              detail)

        # B6 上下文超长 → RAISE，不重试
        c = make_client([_status_error(400, "context_length_exceeded", openai.BadRequestError)])
        e, detail = expect_raise(LLMErrorKind.CONTEXT_LIMIT, c)
        check("context_limit：立即抛出（交执行器压缩），零重试",
              e is not None and e.kind == LLMErrorKind.CONTEXT_LIMIT
              and len(c._raw.chat.completions.kwargs) == 1, detail)

        # B7 空正文 → 提升 token 预算后成功
        c = make_client([("", "stop"), ("补全后的完整正文", "stop")])
        r = c.generate("s", "u", max_tokens=1000)
        tokens = [kw.get("max_tokens") for kw in c._raw.chat.completions.kwargs]
        check("empty_response：自动提升 max_tokens 后成功",
              r == "补全后的完整正文" and tokens[1] >= int(tokens[0] * 1.5), f"tokens={tokens}")

        # B8 截断 → 翻倍 token 后成功
        c = make_client([("半截输出…", "length"), ("完整输出", "stop")])
        r = c.generate("s", "u", max_tokens=1000)
        tokens = [kw.get("max_tokens") for kw in c._raw.chat.completions.kwargs]
        check("output_truncated：翻倍 max_tokens 后成功",
              r == "完整输出" and tokens[1] >= tokens[0] * 2, f"tokens={tokens}")

        # B9 500 服务端错误 → 归 network 可重试，第 2 次成功
        c = make_client([_status_error(500, "internal error", openai.InternalServerError),
                         ("ok", "stop")])
        check("server 5xx：归 network 有限重试后成功",
              c.generate("s", "u") == "ok" and len(c._raw.chat.completions.kwargs) == 2)

        # B10 quota 但备用平台探活成功 → 切换后成功（不暂停）
        c = make_client([_status_error(402, "insufficient_quota", openai.APIStatusError)])

        def switch_to_backup(client, attempted):
            backup = _RawClient([("备用平台正文", "stop")])
            client._client = backup
            client._raw = backup
            return True

        c._switch_platform = lambda attempted: switch_to_backup(c, attempted)
        check("quota 有备用平台：故障切换后成功（不暂停 Run）",
              c.generate("s", "u") == "备用平台正文")
    finally:
        lc.time.sleep = orig_sleep

    # B11 执行器级：quota 无救 → 整 Run 暂停；修复后续跑成功
    orig_build = install_agents(GOOD_TEXTS, raises={n: LLMRequestError(LLMErrorKind.QUOTA, "余额不足")
                                                    for n in
                                                    ["user_insight", "market_analysis",
                                                     "competitor_analysis", "product_design",
                                                     "business_model", "finance", "growth_ops"]})
    pipe = None
    try:
        pipe = CommitteePipeline(report_dir=str(tmp / "b11"), run_store=RunStore(str(tmp / "b11.db")))
        pipe.run(INPUT)
        run = pipe.store.get_run(pipe.current_run_id)
        check("quota：Run 安全暂停（paused）且写明暂停原因",
              run.status == RUN_PAUSED and "额度" in (run.pause_reason or ""),
              f"{run.status}/{run.pause_reason}")
        agent_rows = pipe.store.list_agent_runs(run.run_id)
        attempted = [a for a in agent_rows if a.status == "failed"]
        check("已尝试棒次落 failed 并记录 llm_error_kind",
              len(attempted) >= 1 and all("quota" in (a.error or "") for a in attempted),
              f"failed={len(attempted)}")
    finally:
        AgentSpec.build_agent = orig_build

    # 同库新实例模拟"充值后续跑"
    SPY_CONTEXT.clear()
    tv.CALLS.clear()
    orig_build = install_agents(GOOD_TEXTS)
    try:
        pipe2 = CommitteePipeline(report_dir=str(tmp / "b11"), run_store=RunStore(str(tmp / "b11.db")))
        ctx = pipe2.resume(run.run_id)
        check("暂停 Run 可 resume，续跑后 12 棒 success",
              pipe2.store.get_run(run.run_id).status == RUN_SUCCESS
              and len([r for r in ctx.reports if r.status == STATUS_SUCCESS]) == 12)
    finally:
        AgentSpec.build_agent = orig_build

    # B12 执行器级：auth → 整 Run failed；换 Key 后仍可恢复
    orig_build = install_agents(GOOD_TEXTS, raises={n: LLMRequestError(LLMErrorKind.AUTH, "密钥无效")
                                                    for n in
                                                    ["user_insight", "market_analysis",
                                                     "competitor_analysis", "product_design",
                                                     "business_model", "finance", "growth_ops"]})
    try:
        pipe3 = CommitteePipeline(report_dir=str(tmp / "b12"), run_store=RunStore(str(tmp / "b12.db")))
        pipe3.run(INPUT)
        run3 = pipe3.store.get_run(pipe3.current_run_id)
        check("auth：Run 置 failed 且记录 Key 错误",
              run3.status == RUN_FAILED and "Key" in (run3.error or ""),
              f"{run3.status}/{run3.error[:40]}")
    finally:
        AgentSpec.build_agent = orig_build
    orig_build = install_agents(GOOD_TEXTS)
    try:
        pipe4 = CommitteePipeline(report_dir=str(tmp / "b12"), run_store=RunStore(str(tmp / "b12.db")))
        ctx4 = pipe4.resume(run3.run_id)
        check("failed Run 修复配置后可 resume 到 success",
              pipe4.store.get_run(run3.run_id).status == RUN_SUCCESS
              and len(ctx4.reports) == 12)
    finally:
        AgentSpec.build_agent = orig_build


# ════════════════════════ C 组：崩溃 → orphan 接管 → resume ════════════════════════

def test_c_crash_resume():
    print("\n【验收3】第 4 棒后进程被 kill：新实例 orphan 接管 → resume，已完成棒零 API 调用")
    tmp = Path(tempfile.mkdtemp())
    db = str(tmp / "crash.db")
    report_dir = str(tmp / "reports")

    SPY_CONTEXT.clear()
    tv.CALLS.clear()
    orig_build = install_agents(GOOD_TEXTS)
    run_id = None
    try:
        # —— 进程 1：正常跑到第 4 棒后被 kill -9（不 finish_run）——
        pipe1 = CommitteePipeline(report_dir=report_dir, run_store=RunStore(db))
        run = pipe1.store.create_run(INPUT, registry.stage_specs_tuples(), report_dir=report_dir)
        run_id = run.run_id
        pipe1.store.mark_run_running(run_id)
        for spec in registry.all()[:4]:
            out = pipe1._execute_agent(spec, INPUT, None, run_id=run_id)
            assert out.result.status == STATUS_SUCCESS, f"{spec.name} 未成功"
            # 镜像 _drive 中 _absorb_outcome 的落盘动作（checkpoint 已指 output_path）
            (Path(report_dir) / f"{spec.seq}_{spec.stage_key}.md").write_text(
                out.result.raw_output, encoding="utf-8")
        # 进程消失：run 仍 running，5-12 仍 queued/paused
    finally:
        AgentSpec.build_agent = orig_build

    run_row = RunStore(db).get_run(run_id)
    check("崩溃现场：Run 停留 running（未正常收尾）", run_row.status == "running")

    # —— 进程 2：启动即接管僵死 Run ——
    pipe2 = CommitteePipeline(report_dir=report_dir, run_store=RunStore(db))
    n = pipe2.store.mark_orphaned_runs_paused()
    check("新实例把僵死 Run 接管为 paused（可恢复）",
          n >= 1 and pipe2.store.get_run(run_id).status == RUN_PAUSED)

    SPY_CONTEXT.clear()
    tv.CALLS.clear()
    orig_build = install_agents(GOOD_TEXTS)
    try:
        ctx = pipe2.resume(run_id)
        names1_4 = [s.name for s in registry.all()[:4]]
        names5_12 = [s.name for s in registry.all()[4:]]
        zero = all(tv.CALLS.get(n, 0) == 0 for n in names1_4)
        once = all(tv.CALLS.get(n, 0) == 1 for n in names5_12)
        check("resume：前 4 棒零调用（本地 checkpoint 回读，不花 API）", zero,
              f"calls={ {n: tv.CALLS.get(n, 0) for n in names1_4} }")
        check("resume：后 8 棒各精确执行 1 次", once,
              f"calls={ {n: tv.CALLS.get(n, 0) for n in names5_12} }")
        check("resume 后 Run=success", pipe2.store.get_run(run_id).status == RUN_SUCCESS)
        check("ctx 恢复+续跑共 12 份报告", len(ctx.reports) == 12)
        files = sorted(p.name for p in Path(report_dir).glob("*.md"))
        check("12 棒报告文件 + final_report.md 全部落盘",
              len([f for f in files if f != "final_report.md"]) == 12
              and (Path(report_dir) / "final_report.md").exists(), f"{len(files)} 个 md")
        resumed = [r for r in ctx.reports if r.metadata.get("resumed_from_checkpoint")]
        check("回读棒次带 resumed_from_checkpoint 留痕", len(resumed) == 4, f"got {len(resumed)}")
        # 回读内容与 checkpoint 文件一致
        spec0 = registry.all()[0]
        f0 = (Path(report_dir) / f"{spec0.seq}_{spec0.stage_key}.md").read_text(encoding="utf-8")
        check("回读正文与磁盘 checkpoint 一致", ctx.get_report(spec0.name).raw_output == f0)
    finally:
        AgentSpec.build_agent = orig_build


# ════════════════════════ D 组：失败不连坐 ════════════════════════

def test_d_failure_isolation():
    print("\n【验收4】竞品官永久不合格：单棒 failed；soft 下游 DEGRADED 继续，hard 下游不受连坐")
    tmp = Path(tempfile.mkdtemp())
    SPY_CONTEXT.clear()
    tv.CALLS.clear()
    orig_gen = ba.llm.generate
    orig_build = install_agents(GOOD_TEXTS, first_outputs={"competitor_analysis": BAD_COMPETITOR})
    try:
        # 返工也只产出短文本 → 竞品官必败
        ba.llm.generate = lambda *a, **k: BAD_COMPETITOR
        pipe = CommitteePipeline(report_dir=str(tmp / "d"), run_store=RunStore(str(tmp / "d.db")))
        ctx = pipe.run(INPUT)
        run = pipe.store.get_run(pipe.current_run_id)

        # 图状态以 RunStore 为权威
        db_states = {a.agent_name: a.status for a in pipe.store.list_agent_runs(pipe.current_run_id)}
        check("竞品官 failed", db_states.get("competitor_analysis") == "failed")
        check("红队/总指挥 DEGRADED（soft 依赖竞品失败，仍执行、有产出）",
              db_states.get("red_team") == "degraded"
              and db_states.get("commander") == "degraded",
              f"red_team={db_states.get('red_team')} commander={db_states.get('commander')}")
        unaffected = ["user_insight", "market_analysis", "product_design", "business_model",
                      "finance", "growth_ops", "risk_review", "project_review", "pitch_defense"]
        check("其余 9 棒 success（单棒失败不连坐、不阻断 hard 下游）",
              all(db_states.get(n) == "success" for n in unaffected),
              f"{ {n: db_states.get(n) for n in unaffected if db_states.get(n) != 'success'} }")
        check("DEGRADED 两棒实际调用 1 次（降级≠不执行）",
              tv.CALLS.get("red_team") == 1 and tv.CALLS.get("commander") == 1,
              str({n: tv.CALLS.get(n) for n in ("red_team", "commander")}))
        check("Run 终态=completed_with_errors（降级非完美，不是整 Run failed）",
              run.status == RUN_COMPLETED_WITH_ERRORS, run.status)

        # 业务结果层：degraded 棒 result.status 仍为 success，metadata 留痕缺失输入
        rt_res = ctx.get_report("red_team")
        cm_res = ctx.get_report("commander")
        check("降级棒业务结果 success 且 degraded_inputs 含竞品官",
              rt_res.status == STATUS_SUCCESS
              and rt_res.metadata.get("degraded_inputs") == ["competitor_analysis"]
              and cm_res.metadata.get("degraded_inputs") == ["competitor_analysis"],
              f"rt={rt_res.metadata.get('degraded_inputs')} cm={cm_res.metadata.get('degraded_inputs')}")

        # 图依赖精确化：risk 在第 0 层 context=None；红队/总指挥收到竞品 failed 占位；
        # 评审/路演的 hard 依赖集合不含竞品 → context 中不应出现竞品报告
        check("风险官第 0 层独立运行（context=None）",
              SPY_CONTEXT["risk_review"][0] is None)
        for downstream in ("red_team", "commander"):
            reports = SPY_CONTEXT[downstream][0]["reports"]
            comp = next(r for r in reports if r.agent_name == "competitor_analysis")
            check(f"{downstream} 收到的竞品报告带 failed 标记（不冒充合格）",
                  comp.status == STATUS_FAILED and "校验未通过" in comp.raw_output[:40])
        for downstream in ("project_review", "pitch_defense"):
            names = [r.agent_name for r in SPY_CONTEXT[downstream][0]["reports"]]
            check(f"{downstream} 只收 hard 依赖报告，不含竞品（图精确传参）",
                  "competitor_analysis" not in names, str(names))
        leaked = [d for d in ("red_team", "commander")
                  for r in SPY_CONTEXT[d][0]["reports"]
                  if r.agent_name == "competitor_analysis" and r.status == STATUS_SUCCESS]
        check("不存在任何 soft 下游把竞品坏报告当 success 接收", leaked == [], str(leaked))

        check("stats：degraded=2、blocked=0、skipped=0",
              pipe.stats["degraded_count"] == 2 and pipe.stats["blocked_count"] == 0
              and pipe.stats["skipped_count"] == 0)
        report = (Path(tmp / "d") / "final_report.md").read_text(encoding="utf-8")
        check("最终报告显式记录 failed 与 degraded 图状态",
              "竞品分析官" in report and "failed" in report and "degraded" in report)
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


# ════════════════════════ E 组：红线强制 + 三层结论一致性 ════════════════════════

def _chain_report(name, *, conclusion="", redline=None, blocking=None, forced=False, raw=""):
    md = {}
    if redline is not None:
        md["redline_triggered"] = redline
    if blocking is not None:
        md["blocking"] = blocking
    if forced:
        md["redline_forced_by_system"] = True
    return AgentResult(agent_name=name, status=STATUS_SUCCESS, conclusion=conclusion,
                       raw_output=raw or (conclusion or "") + "。" * 80, metadata=md)


def _chain(risk_blocking=False, review_concl="有条件准入路演", redline=False, forced=False,
           pitch_concl="路演结论：有条件路演，先完成整改项", commander_raw=""):
    reports = [_chain_report("risk_review", blocking=risk_blocking, raw="风险审查报告。" * 30)]
    reports.append(_chain_report("commander", raw=commander_raw or ("项目阶段判断为想法验证阶段。" * 20)))
    reports.append(_chain_report("project_review", conclusion=review_concl, redline=redline, forced=forced))
    reports.append(_chain_report("pitch_defense", conclusion=pitch_concl))
    return reports


def test_e_decision_chain_consistency():
    print("\n【验收5】风险→总指挥→评审→路演 三层结论一致性：冲突可程序检出，红线可强制阻断")

    # E1 正常一致链：无阻断风险、有条件准入、有条件路演
    issues = cross_check_decisions(_chain())
    check("一致链无 error/warning", not issues, str([i.code for i in issues]))

    # E2 风险 blocking=True，评审未触发红线却无条件准入 → 冲突
    issues = cross_check_decisions(_chain(risk_blocking=True, review_concl="准入路演"))
    codes = [i.code for i in issues]
    check("阻断风险 vs 无条件准入 → DECISION_RISK_REVIEW_CONFLICT",
          "DECISION_RISK_REVIEW_CONFLICT" in codes, str(codes))

    # E3 红线被系统强制 + 答辩仍放行 → 冲突
    issues = cross_check_decisions(_chain(risk_blocking=True, review_concl=REDLINE_FORCED_CONCLUSION,
                                          redline=True, forced=True, pitch_concl="结论：可以路演"))
    codes = [i.code for i in issues]
    check("红线强制 vs 可以路演 → DECISION_REDLINE_PITCH_CONFLICT",
          "DECISION_REDLINE_PITCH_CONFLICT" in codes, str(codes))

    # E4 红线后"有条件路演"同样不允许（红线未清不得路演）
    issues = cross_check_decisions(_chain(redline=True, review_concl="暂缓进入修订周期",
                                          pitch_concl="结论：有条件路演"))
    check("红线 vs 有条件路演 同样判冲突",
          "DECISION_REDLINE_PITCH_CONFLICT" in [i.code for i in issues])

    # E5 阻断风险 + 总指挥明确放行 → 冲突
    issues = cross_check_decisions(_chain(
        risk_blocking=True,
        commander_raw="综合判断：风险可控，本项目评审通过，允许进入路演环节。" + "补充说明。" * 20))
    check("阻断风险 vs 总指挥放行 → DECISION_RISK_COMMANDER_CONFLICT",
          "DECISION_RISK_COMMANDER_CONFLICT" in [i.code for i in issues])

    # E6 否定语境："不允许进入路演"不得误判为放行
    issues = cross_check_decisions(_chain(
        risk_blocking=True,
        commander_raw="在合规风险闭环之前，不允许进入路演，必须先完成整改。" + "补充说明。" * 20))
    check("'不允许进入路演'否定句不误伤",
          "DECISION_RISK_COMMANDER_CONFLICT" not in [i.code for i in issues],
          str([i.code for i in issues]))

    # E7 终审准入但答辩暂不建议 → 仅 warning（方向背离留痕，不硬阻断）
    issues = cross_check_decisions(_chain(review_concl="准入路演", pitch_concl="结论：暂不建议路演"))
    codes = [i.code for i in issues]
    check("评审/答辩方向背离给 warning 且无 error",
          "DECISION_REVIEW_PITCH_DIVERGENCE" in codes
          and all(i.severity != "error" for i in issues), str(codes))

    # E8 红线强制改判端到端：红线+准入矛盾文本返工不改 → 系统强制成功 + 结论改判
    tmp = Path(tempfile.mkdtemp())
    orig_gen = ba.llm.generate
    orig_build = install_agents(GOOD_TEXTS, first_outputs={"project_review": RED_CONFLICT_TEXT})
    try:
        ba.llm.generate = lambda *a, **k: RED_CONFLICT_TEXT
        pipe = CommitteePipeline(report_dir=str(tmp / "e8"), run_store=RunStore(str(tmp / "e8.db")))
        out = pipe._execute_agent(registry.get("project_review"), INPUT, None, run_id=None)
        r = out.result
        check("红线矛盾文本返工后仍矛盾：系统强制接受并改判",
              r.status == STATUS_SUCCESS and r.metadata.get("redline_forced_by_system") is True
              and r.conclusion == REDLINE_FORCED_CONCLUSION, r.conclusion[:50])
        # 若此时路演官仍给放行，跨层检查必须拦下
        pitch = _chain_report("pitch_defense", conclusion="结论：可以路演，答辩表现良好")
        issues = cross_check_decisions([_chain_report("risk_review", blocking=True, raw="风险。" * 40),
                                        r, pitch])
        check("强制红线 + 放行答辩 被跨层检查拦下",
              "DECISION_REDLINE_PITCH_CONFLICT" in [i.code for i in issues])
    finally:
        AgentSpec.build_agent = orig_build
        ba.llm.generate = orig_gen


def main():
    tests = [
        ("A", test_a_validator_repair_gate),
        ("B", test_b_llm_error_strategies),
        ("C", test_c_crash_resume),
        ("D", test_d_failure_isolation),
        ("E", test_e_decision_chain_consistency),
    ]
    print("=" * 60)
    print("Phase 7-6 故障注入 / 恢复 / 一致性 离线验收")
    print("=" * 60)
    import traceback
    for _tag, t in tests:
        try:
            t()
        except Exception:
            global _FAILED
            _FAILED += 1
            print(f"  ❌ {t.__name__} 抛异常：")
            traceback.print_exc()
    print("\n" + "=" * 60)
    print(f"结果：{_PASSED} 通过 / {_FAILED} 失败")
    print("=" * 60)
    sys.exit(1 if _FAILED else 0)


if __name__ == "__main__":
    main()
