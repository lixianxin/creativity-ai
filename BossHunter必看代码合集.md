# BossHunter 必看代码合集（面向创想∞迁移）

> 本文档**直接收录需要阅读的代码原文**，按 P0 → P1 排序，配合每段开头的一行「看什么」阅读。代码均摘自 v2.3.2，标注文件与行号。
> 阅读目标只有一个：产出文末的《BossHunter → 创想∞ 技术迁移表》。

## 目录

- **P0**：1 scorer.py ｜ 2 credentials.py ｜ 3 pipeline.py ｜ 4 db.py + run store ｜ 5 tasks.py + server.py ｜ 6 App.tsx + useDashboard.ts
- **P1**：7 greeter.py ｜ 8 resume.py ｜ 9 collection 四件套 + orchestrator ｜ 10 tests
- **P2 暂不读**、**迁移表**

---

# P0-1　`src/bosshunter/ai/scorer.py`（最值得深读）

看什么：①模型只输出分项分、程序求和；②输出不合法整体拒绝；③临界分独立二评、封顶从严取并集；④8 类错误差异化自愈；⑤单条失败不连坐、服务级故障保进度暂停。

### 1.1 五维结构化评分提示词 + 分值上限（L38-L109）

```python
SCORING_PROMPT = """你是一位严谨的招聘匹配评估员。请只依据简历与岗位JD中明确出现的事实进行评估，不补全、不猜测候选人能力。

## 候选人简历
{resume}

## 候选人个人信息
- 最高学历：{candidate_education}
- 求职招聘类型：{candidate_recruitment_type}

## 岗位信息
- 职位：{title}
- 公司：{company}
- 薪资：{salary}
- 要求：{experience}
- 学历要求：{education}
- 招聘类型：{recruitment_type}
- JD：{jd}

## 统一评分维度
逐项给分，不要自行输出总分；程序会统一求和：
1. 核心职责匹配（0-40分）：简历中有明确证据覆盖JD主要日常职责。
2. 可迁移证据（0-25分）：过往成果、工作方法和相邻经验能否迁移到该岗位。
3. 硬性要求（0-15分）：年限、学历、必备技能等明确硬要求的满足程度。
4. 工具与行业（0-10分）：工具、产品类型、客户类型或行业背景；JD仅写“优先/加分”时不能当作硬缺口。
5. 实际条件（0-10分）：城市、薪资、工作方式和稳定性等可判断条件。

## 封顶规则
仅在JD把相关内容作为核心职责或明确必备条件，且简历没有相应证据时填写caps：
- technical_required：必须掌握SQL、Linux、编程、服务器/私有化部署等硬技术，最终最高55分。
- sales_acquisition_core：岗位核心是销售获客、业绩指标或陌生开发，但简历没有对应证据，最终最高65分。
- weak_core_transfer：只有少量辅助职责可迁移，核心工作缺少直接或相邻证据，最终最高70分。
行业“优先”、工具可入职后学习、普通协作事项均不得触发封顶。hard_gaps只写JD明确要求且简历确实缺失的内容。

请严格输出一个JSON对象，不要Markdown，不要额外说明。五个score必须是整数且不得超过各自上限：
{{
  "role_summary": "岗位核心工作概括（40字内）",
  "core_duties": {{"score": 0, "evidence": "简历证据或差距（50字内）"}},
  "transferable_evidence": {{"score": 0, "evidence": "简历证据或差距（50字内）"}},
  "hard_requirements": {{"score": 0, "evidence": "满足情况（50字内）"}},
  "tools_industry": {{"score": 0, "evidence": "匹配情况（50字内）"}},
  "practical_fit": {{"score": 0, "evidence": "匹配情况（50字内）"}},
  "caps": [],
  "hard_gaps": [],
  "reason": "最关键的匹配判断（60字内）",
  "missing": "最关键缺失（40字内，没有则为空）"
}}
"""

REVIEW_PROMPT_SUFFIX = """

## 独立复核
下面是第一次评估结果。请重新核对简历证据与JD，不要迎合第一次结果；仍按上面的同一JSON结构输出各维度分数，不要输出总分。
第一次评估：{first_result}
"""

COMPONENT_LIMITS = {
    "core_duties": 40,
    "transferable_evidence": 25,
    "hard_requirements": 15,
    "tools_industry": 10,
    "practical_fit": 10,
}
# 部分模型（实测 minimaxi M3）会把 transferable_evidence 简写为 transferable，
# 校验前按别名归一，避免有效评分被误判为解析失败（issue #107）。
FIELD_ALIASES = {
    "transferable": "transferable_evidence",
}
CAP_LIMITS = {
    "technical_required": (55, "硬技术缺口封顶55"),
    "sales_acquisition_core": (65, "核心销售获客封顶65"),
    "weak_core_transfer": (70, "核心职责迁移较弱封顶70"),
}
```

结果数据类（L112-L129）：

```python
@dataclass(frozen=True)
class ScoreResult:
    score: int
    raw_score: int
    reason: str
    components: dict[str, int]
    caps: tuple[str, ...]
    summary_reason: str
    missing: str
    structured: bool


@dataclass(frozen=True)
class ScoreOutcome:
    result: ScoreResult | None = None
    failure_detail: str = ""
    pause_reason: str = ""
```

### 1.2 程序求和 + 输出校验闸门（L229-L332）

```python
def _format_structured_reason(
    components: dict[str, int],
    caps: tuple[str, ...],
    summary_reason: str,
    missing: str,
    *,
    reviewed: bool = False,
) -> tuple[int, int, str]:
    raw_score = sum(components.values())
    cap_details = [CAP_LIMITS[cap] for cap in caps if cap in CAP_LIMITS]
    score = min([raw_score, *(limit for limit, _ in cap_details)])
    labels = (
        f"职责{components['core_duties']}/40 · "
        f"证据{components['transferable_evidence']}/25 · "
        f"硬要求{components['hard_requirements']}/15 · "
        f"工具行业{components['tools_industry']}/10 · "
        f"实际条件{components['practical_fit']}/10"
    )
    parts = [f"二次复核后：{labels}" if reviewed else labels]
    if cap_details:
        parts.append("、".join(detail for _, detail in cap_details))
    if summary_reason:
        parts.append(summary_reason)
    reason = "；".join(parts)
    if missing:
        reason = f"{reason} | 缺失: {missing}"
    return score, raw_score, reason


def _structured_score_result(result: dict, *, reviewed: bool = False) -> ScoreResult | None:
    components: dict[str, int] = {}
    for key, limit in COMPONENT_LIMITS.items():
        value = result.get(key)
        if not isinstance(value, dict) or "score" not in value:
            return None
        raw_value = value["score"]
        if isinstance(raw_value, bool):
            return None
        try:
            score = int(raw_value)
        except (TypeError, ValueError):
            return None
        if score != raw_value or not 0 <= score <= limit:
            return None
        components[key] = score

    raw_caps = result.get("caps", [])
    if not isinstance(raw_caps, list):
        return None
    caps = tuple(dict.fromkeys(str(cap) for cap in raw_caps if str(cap) in CAP_LIMITS))
    summary_reason = str(result.get("reason") or "").strip()
    if not summary_reason:
        return None
    missing = str(result.get("missing") or "").strip()
    score, raw_score, reason = _format_structured_reason(
        components, caps, summary_reason, missing, reviewed=reviewed,
    )
    return ScoreResult(
        score=score, raw_score=raw_score, reason=reason, components=components,
        caps=caps, summary_reason=summary_reason, missing=missing, structured=True,
    )


def _apply_field_aliases(result: dict) -> dict:
    """Normalize common model-side field shortenings (e.g. minimaxi M3's `transferable`)."""
    for alias, canonical in FIELD_ALIASES.items():
        if alias in result and canonical not in result:
            result[canonical] = result[alias]
    return result


def _validated_score_result(text: str) -> ScoreResult | None:
    """Accept only complete structured evidence scores."""
    result = _parse_score_response(text)
    if not isinstance(result, dict):
        return None
    _apply_field_aliases(result)
    if all(key in result for key in COMPONENT_LIMITS):
        return _structured_score_result(result)
    return None


def _score_validation_failure_reason(text: str | None) -> str:
    """Explain why a scoring response failed validation, for failure records."""
    if not text or not str(text).strip():
        return "AI 未返回评分内容"
    result = _parse_score_response(text)
    if not isinstance(result, dict):
        return "AI 返回内容无法解析为 JSON"
    _apply_field_aliases(result)
    missing = [key for key in COMPONENT_LIMITS if key not in result]
    if missing:
        return "AI 评分 JSON 缺少字段: " + ", ".join(missing)
    return "AI 评分 JSON 字段值无效（分数或理由不符合格式要求）"
```

### 1.3 临界分二次复核合并：分项平均、封顶从严并集（L335-L367）

```python
def _merge_review_results(first: ScoreResult, review: ScoreResult) -> ScoreResult:
    """Average two independent structured assessments and keep the stricter cap."""
    components = {
        key: (first.components[key] + review.components[key]) // 2
        for key in COMPONENT_LIMITS
    }
    target_raw_score = (first.raw_score + review.raw_score + 1) // 2
    remainder = target_raw_score - sum(components.values())
    for key in COMPONENT_LIMITS:
        if remainder <= 0:
            break
        if (first.components[key] + review.components[key]) % 2:
            components[key] += 1
            remainder -= 1
    caps = tuple(dict.fromkeys((*first.caps, *review.caps)))
    missing = review.missing or first.missing
    score, raw_score, reason = _format_structured_reason(
        components, caps, review.summary_reason, missing, reviewed=True,
    )
    return ScoreResult(
        score=score, raw_score=raw_score, reason=reason, components=components,
        caps=caps, summary_reason=review.summary_reason, missing=missing, structured=True,
    )
```

### 1.4 错误归一化 + 差异化自愈（L415-L526）

```python
def _request_score(
    job: dict, resume: str, config: dict, max_attempts: int,
) -> ScoreOutcome:
    """Request and validate one primary assessment without touching the database."""
    ai_cfg = config.get("ai", {}) if isinstance(config.get("ai"), dict) else {}
    response: str | None = None
    try:
        response = _call_claude(_build_scoring_prompt(job, resume, config), config)
    except AIRequestError as exc:
        if exc.kind == "output_truncated":
            _notify(config, f"{job['company']}｜{job['title']} 的评分回答被截断，正在增大输出 Token 上限后重试。")
            try:
                configured_tokens = int(ai_cfg.get("scoring_max_tokens", 8192) or 8192)
            except (TypeError, ValueError):
                configured_tokens = 8192
            retry_tokens = min(max(configured_tokens * 2, 512), 65536)
            try:
                response = _call_claude(_build_scoring_prompt(job, resume, config), config, retry_tokens)
            except AIRequestError as retry_exc:
                if retry_exc.kind == "empty_response":
                    # 空响应用保持"空结果"语义：落入下方按配置重试，仍空则岗位级失败（#101 回归）。
                    response = None
                elif retry_exc.kind in {"output_truncated", "output_limit", "context_limit"}:
                    return ScoreOutcome(failure_detail="调整输出 Token 后仍未获得完整评分")
                else:
                    # 带上"因截断进入重试"的上下文，否则只看得到重试时的错误（issue #101）。
                    return ScoreOutcome(pause_reason=f"增大输出 Token 重试后失败：{retry_exc}")
        elif exc.kind == "output_limit":
            _notify(config, f"{job['company']}｜{job['title']} 正在降低输出 Token 上限后重试评分。")
            try:
                response = _call_claude(_build_scoring_prompt(job, resume, config), config, 128)
            except AIRequestError as retry_exc:
                if retry_exc.kind == "empty_response":
                    response = None
                elif retry_exc.kind == "output_limit":
                    return ScoreOutcome(failure_detail="当前模型不接受调整后的输出 Token 设置")
                else:
                    return ScoreOutcome(pause_reason=f"降低输出 Token 重试后失败：{retry_exc}")
        elif exc.kind == "context_limit":
            _notify(config, f"{job['company']}｜{job['title']} 内容较长，正在压缩后重试评分。")
            try:
                response = _call_claude(_build_scoring_prompt(job, resume, config, compact=True), config, 128)
            except AIRequestError as retry_exc:
                if retry_exc.kind == "empty_response":
                    response = None
                elif retry_exc.kind == "context_limit":
                    return ScoreOutcome(failure_detail="压缩请求后仍超过模型上下文限制")
                else:
                    return ScoreOutcome(pause_reason=f"压缩请求重试后失败：{retry_exc}")
        elif exc.kind == "empty_response":
            # 空响应用保持"空结果"语义：按 max_attempts 走下方重试，仍为空则只记当前岗位失败，
            # 不中断整批（#101 回归：整批暂停仅留给鉴权/额度/限流/网络等服务级故障）。
            _notify(config, f"{job['company']}｜{job['title']} 的 AI 回答没有文本内容，正在重试。")
            response = None
        else:
            # str(exc) 现在带 kind/status_code，UI 才能区分限流/鉴权/额度等失败原因（issue #101）。
            return ScoreOutcome(pause_reason=str(exc))

    result = _validated_score_result(response) if response else None
    for attempt in range(2, max_attempts + 1):
        if result is not None:
            break
        _notify(
            config,
            f"{job['company']}｜{job['title']} 未返回完整评分，正在重试（{attempt}/{max_attempts}）。",
        )
        try:
            response = _call_claude(_build_scoring_prompt(job, resume, config), config)
        except AIRequestError as retry_exc:
            if retry_exc.kind in {"token_quota", "rate_limit", "auth", "network", "request_failed"}:
                return ScoreOutcome(pause_reason=str(retry_exc))
            response = None
        result = _validated_score_result(response) if response else None

    if result is None:
        return ScoreOutcome(failure_detail=_score_validation_failure_reason(response))
    return ScoreOutcome(result=result)


def _score_job_with_ai(
    job: dict, resume: str, config: dict, max_attempts: int,
) -> ScoreOutcome:
    """Run primary scoring and an optional independent review for borderline results."""
    outcome = _request_score(job, resume, config, max_attempts)
    first = outcome.result
    if first is None or outcome.pause_reason:
        return outcome

    ai_cfg = config.get("ai", {}) if isinstance(config.get("ai"), dict) else {}
    review_enabled = ai_cfg.get("scoring_second_review", False) is True
    if not review_enabled or not first.structured or not 68 <= first.score <= 79:
        return outcome

    try:
        response = _call_claude(_build_review_prompt(job, resume, first, config), config)
    except AIRequestError as exc:
        if exc.kind in {"token_quota", "rate_limit", "auth", "network", "request_failed"}:
            return ScoreOutcome(result=first, pause_reason=str(exc))
        _notify(config, f"{job['company']}｜{job['title']} 二次复核未完成，保留第一次评分。")
        return outcome

    review = _validated_score_result(response) if response else None
    if review is None or not review.structured:
        _notify(config, f"{job['company']}｜{job['title']} 二次复核格式无效，保留第一次评分。")
        return outcome
    return ScoreOutcome(result=_merge_review_results(first, review))
```

### 1.5 主循环：预筛省 token、1–3 并发串行写库、部分成功、断点（L529-L721）

```python
def score_jobs(
    config: dict,
    *,
    scope: str = "pending",
    limit: int | None = None,
    job_ids: list[str] | None = None,
    force_rescore: bool = False,
    rescore_filtered: bool = False,
) -> tuple[int, int]:
    """Score every unscored pending job; previously scored jobs keep their result."""
    db = get_db()
    try:
        resume = _load_resume(config)
        if not resume:
            console.print("[red]无法读取简历文件[/red]")
            return 0, 0

        if rescore_filtered:
            reset_count = reset_ai_filtered_jobs(db)
            _notify(config, f"已将 {reset_count} 个 AI 低分岗位加入重新评分队列。")

        options = validate_options(scope, limit, job_ids, force_rescore)
        pending_jobs = select_scoring_jobs(db, **options)
        # Preserve the lightweight mocked database seam used by legacy tests.
        if not pending_jobs and scope == "pending" and not job_ids:
            legacy_jobs = get_jobs_by_status(db, "pending")
            pending_jobs = legacy_jobs[:limit] if limit is not None else legacy_jobs
        if not pending_jobs:
            console.print("[yellow]没有待评分的岗位[/yellow]")
            return 0, 0

        threshold = config.get("scoring", {}).get("threshold", 60)
        remaining_job_ids = [str(job["id"]) for job in pending_jobs]
        _report_checkpoint(config, remaining_job_ids, status="running")

        def mark_completed(job_id: str) -> None:
            if job_id in remaining_job_ids:
                remaining_job_ids.remove(job_id)
            _report_checkpoint(config, remaining_job_ids, status="running")

        ai_cfg = config.get("ai", {}) if isinstance(config.get("ai"), dict) else {}
        try:
            max_attempts = max(1, min(int(ai_cfg.get("scoring_max_attempts", 2) or 2), 3))
        except (TypeError, ValueError):
            max_attempts = 2
        concurrency = get_scoring_concurrency(config)
        stop_event = config.get("_workbench_stop_event")
        scored = 0
        filtered = 0
        prefiltered = 0
        processed = 0
        failed = 0
        pause_reason = ""

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"评分中 (0/{len(pending_jobs)})", total=len(pending_jobs))
            ai_jobs: list[dict] = []
            for job in pending_jobs:
                if stop_event is not None and stop_event.is_set():
                    break
                qs, qs_reason = quick_score(job, config)
                update_job_quick_score(db, job["id"], qs)
                if qs == 0:
                    update_job_score(db, job["id"], qs, f"预筛不通过: {qs_reason}")
                    update_job_status(db, job["id"], "filtered")
                    filtered += 1
                    prefiltered += 1
                    processed += 1
                    mark_completed(str(job["id"]))
                    progress.update(
                        task, advance=1,
                        description=f"评分中 ({processed}/{len(pending_jobs)}) [预筛淘汰{prefiltered}]",
                    )
                    _report_progress(config, processed, len(pending_jobs), scored, filtered, failed)
                else:
                    ai_jobs.append(job)

            executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="bosshunter-score")
            futures: dict[Future[ScoreOutcome], dict] = {}
            job_iter = iter(ai_jobs)

            def submit_next() -> bool:
                try:
                    next_job = next(job_iter)
                except StopIteration:
                    return False
                future = executor.submit(_score_job_with_ai, next_job, resume, config, max_attempts)
                futures[future] = next_job
                return True

            for _ in range(min(concurrency, len(ai_jobs))):
                submit_next()

            interrupted = False
            while futures:
                if stop_event is not None and stop_event.is_set():
                    interrupted = True
                    break
                done, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                for future in done:
                    job = futures.pop(future)
                    try:
                        outcome = future.result()
                    except OperationCancelled:
                        interrupted = True
                        break
                    except Exception as exc:
                        outcome = ScoreOutcome(failure_detail=f"评分任务异常: {type(exc).__name__}")

                    result = outcome.result
                    completed_job = False
                    if result is not None:
                        update_job_score(db, job["id"], result.score, result.reason)
                        if result.score >= threshold:
                            update_job_status(db, job["id"], "ready")
                            scored += 1
                        else:
                            update_job_status(db, job["id"], "filtered")
                            filtered += 1
                        completed_job = True
                    elif outcome.failure_detail:
                        failed += 1
                        _record_score_failure(db, job, outcome.failure_detail)
                        _notify(config, f"已跳过 {job['company']}｜{job['title']}：{outcome.failure_detail}。")
                        completed_job = True

                    if completed_job:
                        processed += 1
                        mark_completed(str(job["id"]))
                        progress.update(
                            task, advance=1,
                            description=f"评分中 ({processed}/{len(pending_jobs)}) [预筛淘汰{prefiltered}]",
                        )
                        _report_progress(config, processed, len(pending_jobs), scored, filtered, failed)

                    if outcome.pause_reason:
                        pause_reason = outcome.pause_reason
                        interrupted = True
                        break
                    submit_next()
                if interrupted:
                    break

            if interrupted:
                for future in futures:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)

        if prefiltered > 0:
            console.print(f"[dim]  预筛阶段淘汰 {prefiltered} 个岗位（节省 {prefiltered} 次 API 调用）[/dim]")
        if pause_reason:
            _notify(
                config,
                f"AI 评分已安全暂停：{pause_reason}。已完成结果已保存，剩余 {len(remaining_job_ids)} 个岗位下次运行会继续处理。",
                error=True,
            )
        if failed:
            _notify(config, f"本轮有 {failed} 个岗位评分失败并保留为待处理，可稍后重试。")
        if remaining_job_ids:
            _report_checkpoint(
                config,
                remaining_job_ids,
                status="paused",
                pause_reason=pause_reason or "用户暂停或任务中断",
                # pause_reason 非空即 AI 失败暂停（用户停止走 stop_event，reason 为空）。
                error=pause_reason or None,
            )
        else:
            _report_checkpoint(
                config, [],
                status="completed_with_errors" if failed else "completed",
            )
        return scored, filtered
    finally:
        db.close()
```

---

# P0-2　`src/bosshunter/ai/credentials.py`（LLM 基础设施）

看什么：统一错误对象、8 类错误归一的判定顺序、thinking 参数多策略降级、双协议调用入口收敛厂商差异。

### 2.1 统一错误对象（L16-L35）

```python
class AIRequestError(RuntimeError):
    """Normalized AI request failure without exposing credentials or raw payloads."""

    def __init__(self, kind: str, user_message: str, status_code: int | None = None):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code

    # kind/status_code 不进 __str__ 的话，raise 链下游只能拿到兜底文案，
    # UI 永远分不清是限流、鉴权还是额度问题（issue #101）。
    def __str__(self) -> str:
        suffix = f" ({self.kind}" + (f", status={self.status_code}" if self.status_code else "") + ")"
        return self.user_message + suffix
```

### 2.2 8 类错误归一（L89-L157）——注意判定顺序的注释论证

```python
def normalize_ai_error(exc: Exception, response: object | None = None) -> AIRequestError:
    """Classify provider errors into actionable, credential-safe categories."""
    if isinstance(exc, AIRequestError):
        return exc

    resolved_response = response if response is not None else getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None) or getattr(resolved_response, "status_code", None)
    raw = f"{type(exc).__name__} {exc} {_response_error_detail(resolved_response)}".lower()

    output_limit_markers = (
        "max_tokens", "max completion tokens", "maximum output tokens", "tokens to sample",
    )
    context_markers = (
        "context_length", "context length", "maximum context", "max context",
        "input tokens", "prompt tokens", "too many tokens", "prompt is too long",
        "request too large", "上下文", "输入过长",
    )
    quota_markers = (
        "insufficient_quota", "quota exceeded", "token quota", "billing", "balance",
        "credit", "budget", "overdue", "payment required", "余额不足", "额度不足",
    )
    rate_markers = (
        "rate limit", "too many requests", "requests per minute", "tokens per minute",
        " tpm", " rpm", "限流", "频率限制",
    )

    # 判定顺序：明确的 401/403 状态最先归为鉴权——错误体关键词只是启发式，401+「额度」类
    # 混排错误体不应误导恢复建议。其后额度/限流先于上下文：真实错误体常混排多种提示（如
    # "余额不足，请减少输入过长内容"），先查 context marker 会把额度问题误报成上下文超限
    # （issue #101）。quota marker 仍优先于 429 状态码：OpenAI 的 insufficient_quota 实际就配 429 返回。
    if status_code in {401, 403}:
        return AIRequestError("auth", "AI API Key 无效或当前模型没有访问权限", status_code)
    if status_code == 402 or any(marker in raw for marker in quota_markers):
        return AIRequestError("token_quota", "AI Token 额度或账户余额不足", status_code)
    if status_code == 429 or any(marker in raw for marker in rate_markers):
        return AIRequestError("rate_limit", "AI 服务触发请求或 Token 频率限制", status_code)
    if any(marker in raw for marker in context_markers):
        return AIRequestError("context_limit", "请求内容超过当前模型的上下文限制", status_code)
    if any(marker in raw for marker in output_limit_markers):
        return AIRequestError("output_limit", "当前模型不接受设置的输出 Token 上限", status_code)
    if isinstance(exc, httpx.RequestError):
        return AIRequestError("network", "AI 服务连接失败或超时", status_code)
    return AIRequestError("request_failed", "AI 服务请求失败", status_code)
```

### 2.3 thinking 多策略降级（L208-L283）

```python
def _thinking_strategies(
    mode: str, budget: int, max_tokens: int,
) -> list[tuple[dict, int]]:
    """Return Anthropic request strategies without hiding non-compatibility errors."""
    expanded_tokens = max(max_tokens, budget + 1024)
    if mode == "disabled":
        strategies = [({"thinking": {"type": "disabled"}}, max_tokens)]
        if expanded_tokens != max_tokens:
            strategies.append(({"thinking": {"type": "disabled"}}, expanded_tokens))
        return strategies
    if mode == "enabled":
        return [({"thinking": {"type": "enabled", "budget_tokens": budget}}, expanded_tokens)]
    if mode == "auto":
        strategies = [({"thinking": {"type": "disabled"}}, max_tokens)]
        if expanded_tokens != max_tokens:
            strategies.append(({"thinking": {"type": "disabled"}}, expanded_tokens))
        strategies.append(({}, expanded_tokens))
        return strategies
    strategies = [({}, max_tokens)]
    if expanded_tokens != max_tokens:
        strategies.append(({}, expanded_tokens))
    return strategies


def _is_thinking_compatibility_error(exc: Exception, response: object | None = None) -> bool:
    resolved_response = response if response is not None else getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None) or getattr(resolved_response, "status_code", None)
    if status_code not in {400, 404, 422}:
        return False
    raw = f"{exc} {_response_error_detail(resolved_response)}".lower()
    parameter_markers = (
        "thinking", "budget_tokens", "unknown field", "unknown parameter",
        "extra inputs", "not permitted", "unsupported parameter", "unrecognized",
    )
    return any(marker in raw for marker in parameter_markers)
```

### 2.4 双协议调用入口：策略轮询 + 截断/空响应显式报错（L456-L597）

```python
def call_anthropic_text(
    prompt: str, config: dict, max_tokens: int, *,
    timeout: float | None = None, purpose: str | None = None,
) -> str | None:
    """Call Anthropic-compatible Messages API and return the first text block."""
    ai_cfg = config.get("ai", {})
    if ai_cfg.get("provider") == "openai_compatible":
        return call_openai_compatible_text(prompt, config, max_tokens, timeout=timeout, purpose=purpose)

    try:
        import anthropic
    except ImportError:
        return None

    if not get_anthropic_api_key(config):
        return None

    model = resolve_anthropic_model(ai_cfg.get("model", "claude-sonnet-4-6"), config)
    client = anthropic.Anthropic(**build_anthropic_client_kwargs(config))
    mode, budget = resolve_thinking_options(config, purpose)
    strategies = _thinking_strategies(mode, budget, max_tokens)
    thinking_rejected = False
    compatibility_error: Exception | None = None
    output_truncated = False
    for overrides, token_limit in strategies:
        if thinking_rejected and "thinking" in overrides:
            continue
        request_kwargs = {
            "model": model,
            "max_tokens": token_limit,
            "messages": [{"role": "user", "content": prompt}],
            **overrides,
        }
        if timeout is not None:
            request_kwargs["timeout"] = _coerce_timeout(timeout)
        try:
            response = client.messages.create(**request_kwargs)
        except Exception as exc:
            if _is_thinking_compatibility_error(exc):
                thinking_rejected = True
                compatibility_error = exc
                continue
            raise normalize_ai_error(exc) from exc
        if getattr(response, "stop_reason", None) == "max_tokens":
            output_truncated = True
            continue
        text = _extract_text_content(getattr(response, "content", None))
        if text:
            return text
    if output_truncated:
        raise AIRequestError("output_truncated", "AI 返回内容因输出 Token 上限被截断")
    if compatibility_error is not None:
        raise normalize_ai_error(compatibility_error) from compatibility_error
    # 所有策略都没有产出文本时显式报错：静默 return None 会让调用方把
    # thinking-only 响应记成无理由失败，截断和空响应全都不可见（issue #102）。
    raise AIRequestError("empty_response", "AI 服务没有返回文本内容，可能只返回了思考过程")
```

OpenAI 兼容入口 `call_openai_compatible_text`（L524-L597）结构完全同构：同样的策略轮询、`finish_reason in {"length","max_tokens"}` 判截断、thinking-only 显式报 `empty_response`，错误一律走 `normalize_ai_error(exc, response)`。8 类归一的完整类别：`auth / token_quota / rate_limit / context_limit / output_limit / output_truncated / empty_response / network`（外加兜底 `request_failed`）。

模型能力探测见 `resolve_anthropic_model`（L420-L453）：自定义 base_url 时调 `/v1/models` 拉真实 ID 列表做模糊匹配，结果按 `(base_url, model, key指纹)` 缓存，探测失败则原样使用不阻断。

---

# P0-3　`src/bosshunter/pipeline.py`（全文 109 行）

看什么：**薄编排**。没有上下文对象、没有 DAG 框架；步骤之间不传内存状态，全部靠 SQLite 的 status 字段流转，因此天然可重入、部分成功。

```python
"""Pipeline - orchestrates the full BossHunter flow."""

from rich.console import Console

from bosshunter.browser import check_chrome_connection, configure, find_boss_tab

console = Console()


def run_pipeline(config: dict) -> None:
    """Run the full pipeline: scrape → score → confirm → greet → send → monitor."""
    configure(config)

    # Step 1: Check Browser Runtime connection
    console.print("[bold]Step 1/6: 检测 Browser Runtime[/bold]")
    version_info = check_chrome_connection()
    if not version_info:
        console.print("[red]✗ Browser Runtime 未连接，请先运行 bosshunter connect 查看诊断[/red]")
        return

    boss_tab = find_boss_tab()
    if not boss_tab:
        console.print("[red]✗ 未发现 BOSS直聘 页面，请先登录[/red]")
        return
    console.print("[green]  ✓ 浏览器就绪[/green]\n")

    # Step 2: Scrape jobs
    console.print("[bold]Step 2/6: 采集岗位[/bold]")
    from bosshunter.scraper.jobs import scrape_jobs
    keywords = config["search"]["keywords"]
    collected_job_ids: list[str] = []
    count = scrape_jobs(config, keywords, collected_job_ids=collected_job_ids)
    if count == 0:
        console.print("[yellow]  ! 未采集到新岗位，尝试继续处理已有岗位...[/yellow]")
    else:
        console.print(f"[green]  ✓ 采集 {count} 个新岗位[/green]\n")

    # Step 3: AI scoring (with pre-filter)
    console.print("[bold]Step 3/6: AI 评分筛选[/bold]")
    from bosshunter.ai.scorer import score_jobs
    scored, filtered = score_jobs(config)
    if scored == 0 and count > 0:
        console.print("[yellow]  ! 没有通过评分的岗位，流程结束[/yellow]")
        return
    console.print(f"[green]  ✓ {scored} 个通过, {filtered} 个过滤[/green]\n")

    # Step 4: Confirm which jobs to pursue
    console.print("[bold]Step 4/6: 确认投递清单[/bold]")
    from bosshunter.ui.confirm import show_confirmation
    approved = show_confirmation(config)
    if not approved:
        console.print("[yellow]  已取消发送[/yellow]")
        return

    # Step 5: Generate greetings for confirmed jobs, then send
    console.print("\n[bold]Step 5/6: 生成招呼语并发送[/bold]")
    from bosshunter.ai.greeter import generate_greetings
    greet_count = generate_greetings(config)
    console.print(f"[green]  ✓ 生成 {greet_count} 条招呼语[/green]")

    from bosshunter.executor.sender import send_greetings
    sent = send_greetings(config)
    console.print(f"\n[bold green]═══ 发送完成！{sent} 条招呼语 ═══[/bold green]")

    # Step 6: Auto-start monitor loop
    console.print("\n[bold]Step 6/6: 启动持续监测[/bold]")
    from bosshunter.executor.monitor import (
        get_effective_monitor_interval_minutes,
        monitor_and_send_resumes,
    )

    interval_min = get_effective_monitor_interval_minutes(config)
    interval_sec = interval_min * 60
    console.print(f"[dim]每 {interval_min:g} 分钟检查一次HR回复和跟进，按 Ctrl+C 停止[/dim]\n")

    import time

    try:
        raw_cooldown = config.get("monitor", {}).get("initial_cooldown_minutes", 10)
        try:
            initial_cooldown_sec = max(float(raw_cooldown), 0) * 60
        except (TypeError, ValueError):
            initial_cooldown_sec = 10 * 60
        if initial_cooldown_sec > 0:
            console.print(
                f"[dim]发送结束后先冷却 {initial_cooldown_sec / 60:g} 分钟；按 Ctrl+C 可取消[/dim]\n"
            )
            time.sleep(initial_cooldown_sec)
        while True:
            try:
                summary = monitor_and_send_resumes(config)
                parts = []
                if summary.get("replied"):
                    parts.append(f"回复{summary['replied']}条")
                if summary.get("follow_up"):
                    parts.append(f"跟进{summary['follow_up']}条")
                if summary.get("needs_resume"):
                    parts.append(f"[bold yellow]待手动发简历{summary['needs_resume']}份[/bold yellow]")
                if parts:
                    console.print(f"  本轮: {', '.join(parts)}")
                if summary.get("stop_reason"):
                    console.print("[red]监测检测到风险信号，已安全停止[/red]")
                    break
            except Exception as e:
                console.print(f"[red]  监测出错: {e}[/red]")
            console.print(f"[dim]  下次检查: {interval_min:g} 分钟后...[/dim]\n")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        console.print("\n[yellow]已停止监测[/yellow]")
```

---

# P0-4　`src/bosshunter/db.py` + `scoring_run_store.py`（状态机 / 迁移 / Checkpoint）

看什么：五种状态分五张表（jobs 状态机、history 流水、risk/access 计数、safety 单行锁、runs 断点）；无迁移工具的幂等 ALTER 升级；run 的 orphan 接管。

### 4.1 核心表结构（db.py L51-L125）

```python
def _init_tables(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            salary TEXT,
            city TEXT,
            experience TEXT,
            education TEXT,
            recruitment_type TEXT DEFAULT 'unknown',
            jd TEXT,
            hr_name TEXT,
            hr_title TEXT,
            hr_active TEXT,
            company_size TEXT,
            company_industry TEXT,
            url TEXT,
            score INTEGER DEFAULT 0,
            score_reason TEXT,
            greeting TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS risk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS platform_access_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL DEFAULT 'boss',
            stage TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS platform_safety_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            reason TEXT NOT NULL,
            locked_until TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score);
        CREATE INDEX IF NOT EXISTS idx_history_job_id ON history(job_id);
        CREATE INDEX IF NOT EXISTS idx_risk_events_type ON risk_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_platform_access_stage_action
            ON platform_access_events(stage, action, created_at);
    """)
    conn.commit()
    _migrate_v1_1(conn)
    _migrate_v1_2(conn)
    _migrate_v1_3(conn)
    _migrate_v1_4(conn)
    _migrate_platform_access_events(conn)
    _init_scoring_runs(conn)
    _init_collection_runs(conn)
    _init_collect_progress(conn)
```

### 4.2 无迁移工具的幂等迁移（L563-L650）

```python
def _migrate_v1_1(conn: sqlite3.Connection) -> None:
    """Add v1.1 columns if they don't exist."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "quick_score" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN quick_score INTEGER DEFAULT 0")
    if "resume_path" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN resume_path TEXT DEFAULT NULL")
    conn.commit()


def _migrate_v1_2(conn: sqlite3.Connection) -> None:
    """Add recycle-bin metadata without rebuilding or rewriting job rows."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN deleted_at TIMESTAMP NULL")
    if "deleted_reason" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN deleted_reason TEXT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_deleted_at ON jobs(deleted_at)")
    conn.commit()


def _migrate_v1_3(conn: sqlite3.Connection) -> None:
    """Add source identity columns without rewriting existing BOSS ids."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    additions = {
        "source_platform": "TEXT NOT NULL DEFAULT 'boss'",
        "source_job_id": "TEXT NULL",
        "source_keyword": "TEXT NULL",
        "source_city_code": "TEXT NULL",
    }
    for name, definition in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_identity
        ON jobs(source_platform, source_job_id)
        WHERE source_job_id IS NOT NULL AND TRIM(source_job_id) <> ''
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source_platform ON jobs(source_platform)")
    conn.commit()


def _migrate_v1_4(conn: sqlite3.Connection) -> None:
    """Add education and recruitment-type fields without aggressive inference."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "education" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN education TEXT")
    if "recruitment_type" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN recruitment_type TEXT DEFAULT 'unknown'")
    searchable = "COALESCE(title, '') || ' ' || COALESCE(jd, '') || ' ' || COALESCE(experience, '')"
    conn.execute(f"""
        UPDATE jobs SET education = CASE
            WHEN {searchable} LIKE '%博士%' THEN '博士'
            WHEN {searchable} LIKE '%硕士%' THEN '硕士'
            WHEN {searchable} LIKE '%本科%' THEN '本科'
            WHEN {searchable} LIKE '%大专%' OR {searchable} LIKE '%专科%' THEN '大专'
            WHEN {searchable} LIKE '%学历不限%' OR {searchable} LIKE '%不限学历%' THEN '不限'
            ELSE education
        END
        WHERE education IS NULL OR TRIM(education) = ''
    """)
    conn.execute(f"""
        UPDATE jobs SET recruitment_type = CASE
            WHEN {searchable} LIKE '%校招%' OR {searchable} LIKE '%校园招聘%'
              OR {searchable} LIKE '%应届%' OR {searchable} LIKE '%毕业生%'
              OR {searchable} LIKE '%管培生%' OR {searchable} LIKE '%实习生%' THEN 'campus'
            WHEN {searchable} LIKE '%社招%' OR {searchable} LIKE '%社会招聘%' THEN 'experienced'
            ELSE 'unknown'
        END
        WHERE recruitment_type IS NULL OR TRIM(recruitment_type) = '' OR recruitment_type = 'unknown'
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_recruitment_type ON jobs(recruitment_type)")
    conn.commit()
```

### 4.3 两类长任务的 run 表（L652-L689）

```python
def _init_scoring_runs(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scoring_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            status TEXT NOT NULL,
            options_json TEXT NOT NULL,
            remaining_job_ids_json TEXT NOT NULL,
            progress_json TEXT NOT NULL,
            pause_reason TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scoring_runs_status ON scoring_runs(status);
        """
    )
    conn.commit()


def _init_collection_runs(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS collection_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            status TEXT NOT NULL,
            options_json TEXT NOT NULL,
            platform_states_json TEXT NOT NULL,
            collected_job_ids_json TEXT NOT NULL,
            current_platform TEXT,
            stop_reason TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL
        );
        -- （后接状态索引，结构与 scoring_runs 同构）
        """
    )
```

### 4.4 Run Store：更新保护 + 僵死 run 接管（`scoring_run_store.py` 全文关键部分）

```python
TERMINAL_RUN_STATUSES = {"completed", "completed_with_errors", "failed", "stopped"}


def create_scoring_run(
    db_path: Path, *, run_id: str, options: dict[str, Any], job_ids: list[str],
) -> dict[str, Any]:
    db = get_db(db_path)
    try:
        db.execute(
            """INSERT INTO scoring_runs
               (id, status, options_json, remaining_job_ids_json, progress_json)
               VALUES (?, 'pending', ?, ?, ?)""",
            (
                run_id,
                _json_text(options, {}),
                _json_text(job_ids, []),
                _json_text({"selected": len(job_ids), "completed": 0}, {}),
            ),
        )
        db.commit()
        return get_scoring_run(db_path, run_id) or {}
    finally:
        db.close()


def update_scoring_run(
    db_path: Path, run_id: str,
    *, status: str | None = None, task_id: str | None = None,
    remaining_job_ids: list[str] | None = None, progress: dict[str, Any] | None = None,
    pause_reason: str | None = None, error: str | None = None,
) -> dict[str, Any] | None:
    sets = ["updated_at = CURRENT_TIMESTAMP"]
    params: list[Any] = []
    for column, value in (("status", status), ("task_id", task_id), ("pause_reason", pause_reason), ("error", error)):
        if value is not None:
            sets.append(f"{column} = ?")
            params.append(str(value)[:1000])
    if remaining_job_ids is not None:
        sets.append("remaining_job_ids_json = ?")
        params.append(_json_text(remaining_job_ids, []))
    if progress is not None:
        sets.append("progress_json = ?")
        params.append(_json_text(progress, {}))
    if status in TERMINAL_RUN_STATUSES:
        sets.append("finished_at = CURRENT_TIMESTAMP")
    elif status == "running":
        sets.extend(["finished_at = NULL", "pause_reason = NULL", "error = NULL"])
    params.append(run_id)
    where = "id = ?"
    if status in {"running", "paused"}:
        # 终态 run 不允许被回写覆盖
        where += " AND status NOT IN ('completed', 'completed_with_errors', 'failed', 'stopped')"
    db = get_db(db_path)
    try:
        db.execute(f"UPDATE scoring_runs SET {', '.join(sets)} WHERE {where}", params)
        db.commit()
    finally:
        db.close()
    return get_scoring_run(db_path, run_id)


def mark_orphaned_scoring_runs_paused(db_path: Path) -> int:
    """应用启动时调用：进程异常退出留下的 pending/running run 一律转为可恢复暂停态。"""
    db = get_db(db_path)
    try:
        cursor = db.execute(
            """UPDATE scoring_runs
               SET status = 'paused', pause_reason = '应用已重启，可从剩余岗位继续', updated_at = CURRENT_TIMESTAMP
               WHERE status IN ('pending', 'running')"""
        )
        db.commit()
        return cursor.rowcount
    finally:
        db.close()
```

`_public_row` 还会计算一个直接给 UI 用的派生字段：`recoverable = status == "paused" and bool(remaining_job_ids)`。

---

# P0-5　`src/bosshunter/web/tasks.py`（全文）+ `web/server.py` 关键段

看什么：任务对象（快照）、单活动任务守卫、协作式停止 Event、异常只落入快照不炸线程、截止时间 Timer；server 侧的 checkpoint 回调与 REST 路由。

### 5.1 WorkbenchTask / Runner（tasks.py 全文）

```python
"""Workbench background task runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Event, Lock, Thread, Timer
from typing import Any, Callable
from uuid import uuid4

from bosshunter.throttle import SendWindowChecker


MODE_LABELS = {
    "full": "运行全流程",
    "collect": "单独采集",
    "score": "单独 AI 评分",
    "rescore": "重新评分",
    "monitor": "单独监测",
    "deliver": "确认投递",
}

TERMINAL_STATUSES = {"completed", "failed", "stopped"}
ACTIVE_STATUSES = {"running", "stopping"}
DEADLINE_MODES = {"full", "monitor", "deliver"}


class TaskAlreadyRunningError(RuntimeError):
    """Raised when a mutually exclusive workbench task is already active."""


@dataclass
class WorkbenchTask:
    id: str
    mode: str
    label: str
    status: str = "running"
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    deadline_at: str | None = None
    stop_reason: str | None = None
    stop_requested: Event = field(default_factory=Event, repr=False)
    metrics: dict[str, int] = field(default_factory=dict)
    progress: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict, repr=False)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "label": self.label,
            "status": self.status,
            "logs": list(self.logs),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deadline_at": self.deadline_at,
            "stop_reason": self.stop_reason,
            "stop_requested": self.stop_requested.is_set(),
            "metrics": dict(self.metrics),
            "progress": dict(self.progress),
        }


Executor = Callable[[WorkbenchTask, dict], None]


class WorkbenchTaskRunner:
    def __init__(self, executors: dict[str, Executor] | None = None):
        self._executors = executors or {}
        self._tasks: dict[str, WorkbenchTask] = {}
        self._threads: dict[str, Thread] = {}
        self._deadline_timers: dict[str, Timer] = {}
        self._lock = Lock()

    def start(self, mode: str, config: dict) -> dict:
        if mode not in MODE_LABELS:
            raise ValueError(f"Unsupported workbench mode: {mode}")

        with self._lock:
            active = self._active_task_locked()
            if active:
                raise TaskAlreadyRunningError(
                    f"当前已有后台任务「{active.label}」正在运行或停止中，请等待其完全结束"
                )

            task = WorkbenchTask(id=str(uuid4()), mode=mode, label=MODE_LABELS[mode])
            deadline = _deadline_from_config(mode, config)
            if deadline:
                task.deadline_at = deadline.isoformat(timespec="seconds")
            self._tasks[task.id] = task

            if deadline and deadline <= datetime.now():
                task.stop_requested.set()
                task.status = "stopped"
                task.stop_reason = "今日发送时间窗口已截止，后台未启动"
                task.logs.append(task.stop_reason)
                task.updated_at = datetime.now().isoformat(timespec="seconds")
                return task.snapshot()

            thread = Thread(target=self._run, args=(task, config), daemon=True)
            self._threads[task.id] = thread
            if deadline:
                delay_seconds = max((deadline - datetime.now()).total_seconds(), 0)
                timer = Timer(delay_seconds, self._stop_at_deadline, args=(task.id,))
                timer.daemon = True
                self._deadline_timers[task.id] = timer
                timer.start()
            thread.start()
            return task.snapshot()

    def status(self) -> dict:
        with self._lock:
            active = self._active_task_locked()
            tasks = [task.snapshot() for task in self._tasks.values()]
            return {
                "active": active.snapshot() if active else None,
                "last_task": tasks[-1] if tasks else None,
                "tasks": tasks,
            }

    def stop(self, task_id: str, reason: str = "用户已请求停止") -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            if task.status in TERMINAL_STATUSES:
                return task.snapshot()
            task.stop_requested.set()
            task.status = "stopping"
            task.stop_reason = reason
            if reason and (not task.logs or task.logs[-1] != reason):
                task.logs.append(reason)
            task.updated_at = datetime.now().isoformat(timespec="seconds")
            confirmation_event = task.context.get("confirmation_event")
            if isinstance(confirmation_event, Event):
                confirmation_event.set()
            monitor_wakeup_event = task.context.get("monitor_wakeup_event")
            if isinstance(monitor_wakeup_event, Event):
                monitor_wakeup_event.set()
            return task.snapshot()

    def wait(self, timeout: float | None = None) -> None:
        threads = list(self._threads.values())
        for thread in threads:
            thread.join(timeout=timeout)

    def _run(self, task: WorkbenchTask, config: dict) -> None:
        try:
            executor = self._executors.get(task.mode)
            if executor:
                executor(task, config)
            with self._lock:
                if task.stop_requested.is_set():
                    task.status = "stopped"
                else:
                    task.status = "completed"
                task.updated_at = datetime.now().isoformat(timespec="seconds")
        except Exception as exc:
            with self._lock:
                if task.stop_requested.is_set():
                    task.status = "stopped"
                    task.error = None
                else:
                    task.status = "failed"
                    task.error = str(exc)
                task.updated_at = datetime.now().isoformat(timespec="seconds")
        finally:
            with self._lock:
                timer = self._deadline_timers.pop(task.id, None)
            if timer:
                timer.cancel()

    def _stop_at_deadline(self, task_id: str) -> None:
        try:
            self.stop(task_id, "已到发送时间窗口截止时间，后台自动停止")
        except KeyError:
            return

    def _active_task_locked(self) -> WorkbenchTask | None:
        for task in self._tasks.values():
            if task.status in ACTIVE_STATUSES:
                return task
        return None


def _deadline_from_config(mode: str, config: dict) -> datetime | None:
    """Resolve the automatic stop deadline for long-running/send tasks."""
    if mode not in DEADLINE_MODES:
        return None
    throttle = config.get("throttle", {}) if isinstance(config, dict) else {}
    windows = throttle.get("send_windows", [])
    if not isinstance(windows, list):
        return None
    return SendWindowChecker(windows).latest_end_datetime()
```

### 5.2 server.py：进度/断点回调注入业务执行器（L293-L322, L396-L451）

```python
def _log(task: WorkbenchTask, message: str) -> None:
    task.logs.append(message)


def _record_collect_progress(task: WorkbenchTask, state: dict) -> None:
    task.metrics.update({
        "collect_seen": int(state.get("seen") or 0),
        "collect_new": int(state.get("new") or 0),
        "collect_duplicate": int(state.get("duplicate") or 0),
        "collect_filtered": int(state.get("filtered") or 0),
        "collect_parse_failed": int(state.get("parse_failed") or 0),
        "collect_save_failed": int(state.get("save_failed") or 0),
        "collect_search_pages": int(state.get("search_pages") or 0),
    })
    if isinstance(state.get("progress"), dict):
        task.progress = deepcopy(state["progress"])


def _record_score_progress(task: WorkbenchTask, state: dict) -> None:
    task.metrics.update({
        "ai_completed": int(state.get("completed") or 0),
        "ai_total": int(state.get("total") or 0),
        "ai_passed": int(state.get("scored") or 0),
        "ai_filtered": int(state.get("filtered") or 0),
        "ai_failed": int(state.get("failed") or 0),
    })
    _log(
        task,
        f"AI 评分进度 {state['completed']}/{state['total']}：通过 {state['scored']}，过滤 {state['filtered']}，失败 {state['failed']}",
    )


def _execute_score(task: WorkbenchTask, config: dict) -> None:
    from bosshunter.ai.scorer import score_jobs

    run_id = str(config.get("_score_run_id") or "")
    options = config.get("_score_options", {}) if isinstance(config.get("_score_options"), dict) else {}
    db_path = DATA_DIR / "bosshunter.db"

    def checkpoint(state: dict) -> None:
        remaining = [str(job_id) for job_id in state.get("remaining_job_ids", []) if str(job_id)]
        status = str(state.get("status") or "running")
        pause_reason = str(state.get("pause_reason") or "") if status == "paused" else None
        # AI 失败暂停时同步写入 error 列与 task.error，前端任务列表才能看到真实原因（issue #100）。
        error = str(state.get("error") or "") if status == "paused" else None
        update_scoring_run(
            db_path, run_id,
            status=status,
            remaining_job_ids=remaining,
            progress={**task.metrics, "remaining": len(remaining)},
            pause_reason=pause_reason,
            error=error or None,
        )
        if status == "paused":
            task.stop_reason = str(state.get("pause_reason") or "评分任务已暂停")
            if error:
                task.error = error
            task.stop_requested.set()

    score_config = dict(config)
    score_config["_workbench_stop_event"] = task.stop_requested
    score_config["_workbench_log"] = lambda message: _log(task, message)
    score_config["_workbench_score_progress"] = lambda state: _record_score_progress(task, state)
    score_config["_workbench_score_checkpoint"] = checkpoint
    _log(task, f"开始单独 AI 评分：{len(options.get('job_ids', []))} 个岗位")
    try:
        score_jobs(
            score_config,
            scope="selected",
            limit=None,
            job_ids=list(options.get("job_ids", [])),
            force_rescore=bool(options.get("force_rescore")),
        )
    except Exception as exc:
        update_scoring_run(db_path, run_id, status="failed", error=str(exc)[:1000])
        raise
```

注意这条注入链：**Runner 只管线程/状态，业务执行器把 stop_event 与回调塞进 config 字典，scorer/orchestrator 完全不知道 Web 的存在**（私有键 `_workbench_*` 接缝）。

### 5.3 server.py：状态聚合 API + 启停路由（L1186-L1228, L1436-L1520）

```python
@app.route("/api/workbench")
def api_workbench():
    db = _get_web_db()
    try:
        config = load_config(CONFIG_PATH)
        threshold = config.get("scoring", {}).get("threshold", 60)
        daily_limit = int(config.get("throttle", {}).get("daily_limit", 30) or 30)
        today_sent_row = db.execute(
            "SELECT COUNT(*) AS cnt FROM history WHERE action='sent' AND date(created_at)=date('now')"
        ).fetchone()
        today_sent = int(today_sent_row["cnt"] if today_sent_row else 0)
        status = task_runner.status()
        return _json_response({
            "funnel": get_funnel_stats(db),
            "funnel_today": get_funnel_stats(db, today=True),
            "pending_confirmation": [
                job for job in get_jobs_pending_confirmation(db)
                if int(job.get("score") or 0) >= threshold
                and platform_supports(str(job.get("source_platform") or "boss"), "deliver")
            ],
            "pending_greetings": [
                job for job in get_jobs_ready_to_send(db)
                if platform_supports(str(job.get("source_platform") or "boss"), "deliver")
            ],
            "send_errors": [
                job for job in get_jobs_with_send_errors(db)
                if platform_supports(str(job.get("source_platform") or "boss"), "deliver")
            ],
            "needs_resume": [
                job for job in get_jobs_needing_resume(db)
                if platform_supports(str(job.get("source_platform") or "boss"), "deliver")
            ],
            "send_quota": {
                "daily_limit": daily_limit,
                "sent": today_sent,
                "remaining": max(daily_limit - today_sent, 0),
                "exhausted": today_sent >= daily_limit,
            },
            "task": status["active"],
            "last_task": status["last_task"],
        })
    finally:
        db.close()
```

```python
@app.route("/api/workbench/task", method="POST")
def api_workbench_task_start():
    try:
        body = request.json or {}
        if not isinstance(body, dict):
            return _json_response({"error": "请求体必须是对象"}, 400)
        mode = str(body.get("mode", ""))
        base_config = load_config(CONFIG_PATH)
        options = body.get("options") if isinstance(body.get("options"), dict) else None
        collection_options = None
        if mode == "collect":
            try:
                collection_options = normalize_collection_options(base_config, options)
            except ValueError as exc:
                return _json_response({"error": str(exc)}, 400)
        elif mode == "full":
            try:
                collection_options = normalize_collection_options(base_config, options)
            except ValueError as exc:
                return _json_response({"error": str(exc)}, 400)
            collection_only = [
                platform for platform in collection_options["platform_order"]
                if not platform_supports(platform, "deliver")
            ]
            if collection_only:
                return _json_response({
                    "error": "智联和前程无忧当前只支持单独采集，不能进入发送全流程",
                    "collection_only_platforms": collection_only,
                }, 400)
            collection_options["auto_score"] = True
        messages = _preflight_messages(mode, base_config, collection_options)
        if messages:
            return _json_response({"error": "请先处理启动前检查", "messages": messages}, 400)
        extra = {"_collection_options": collection_options} if collection_options is not None else {}
        # ……（非敏感采集偏好持久化到 config，略）……
        with job_mutation_lock:
            task = task_runner.start(mode, _task_config(extra))
        return _json_response(task)
    except TaskAlreadyRunningError as e:
        return _json_response({"error": str(e)}, 409)
    except Exception as e:
        return _json_response({"error": str(e)}, 500)


@app.route("/api/workbench/task/<task_id>/stop", method="POST")
def api_workbench_task_stop(task_id):
    try:
        return _json_response(task_runner.stop(task_id))
    # ……
```

---

# P0-6　前端：`App.tsx`（全文）+ `hooks/useDashboard.ts`（全文）

看什么：App.tsx 只是 35 行路由壳；**真正的任务状态轮询在 useDashboard**——并发拉取、防重入 ref、按页面区分轮询间隔、页面隐藏时不轮询、动作后主动刷新。

### 6.1 App.tsx（全文）

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import DashboardPage from './pages/DashboardPage'
import ConfigPage from './pages/ConfigPage'

function JobsPage() {
  return <DashboardPage view="jobs" />
}

function MonitorPage() {
  return <DashboardPage view="monitor" />
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-background text-foreground">
        <Sidebar />
        <div className="min-w-0 flex-1 flex flex-col overflow-hidden">
          <Header />
          <main className="min-w-0 flex-1 overflow-y-auto p-6">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/monitor" element={<MonitorPage />} />
              <Route path="/config" element={<ConfigPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
```

### 6.2 useDashboard.ts（全文，任务状态轮询核心）

```ts
import { useCallback, useState, useEffect, useRef } from 'react'

// ……（Job / FunnelData / HistoryItem 等 interface 声明略，见源文件 L3-L135）……

export interface WorkbenchTask {
  id: string
  mode: 'full' | 'collect' | 'rescore' | 'monitor' | 'deliver'
  label: string
  status: string
  logs: string[]
  error?: string
  deadline_at?: string
  stop_reason?: string
  stop_requested: boolean
  metrics?: Record<string, number>
  progress?: CollectionProgress
}

export function useDashboard(scope: DashboardDataScope = 'all') {
  const [workbench, setWorkbench] = useState<WorkbenchData>(emptyWorkbench)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)
  const refreshingRef = useRef(false)

  const fetchAll = useCallback(async () => {
    if (refreshingRef.current) return
    refreshingRef.current = true
    setRefreshing(true)
    try {
      const needsWorkbench = scope === 'all' || scope === 'workbench'
      const needsHistory = scope === 'all' || scope === 'monitor'
      const fetchOptions = { cache: 'no-store' as const }
      const [workbenchRes, historyRes] = await Promise.all([
        needsWorkbench ? fetch('/api/workbench', fetchOptions) : Promise.resolve(null),
        needsHistory ? fetch('/api/history?limit=50&include_unresolved=1&include_monitor_conversations=1', fetchOptions) : Promise.resolve(null),
      ])
      const [workbenchData, historyData] = await Promise.all([
        workbenchRes ? workbenchRes.json() : Promise.resolve(undefined),
        historyRes ? historyRes.json() : Promise.resolve(undefined),
      ])

      if (workbenchData !== undefined) setWorkbench(workbenchData)
      if (historyData !== undefined) setHistory(historyData)
      setLastRefreshedAt(new Date())
      setError('')
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err)
      setError('无法读取本地控制台数据')
    } finally {
      refreshingRef.current = false
      setRefreshing(false)
      setLoading(false)
    }
  }, [scope])

  const startTask = async (mode: 'full' | 'collect' | 'rescore' | 'monitor' | 'deliver', options?: Record<string, unknown>) => {
    const res = await fetch('/api/workbench/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, ...(options ? { options } : {}) }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      const details = Array.isArray(data.messages) ? data.messages.map(String).filter(Boolean).join('；') : ''
      throw new Error([data.error || '启动失败', details].filter(Boolean).join('：'))
    }
    const task = await res.json() as WorkbenchTask
    setWorkbench(prev => ({ ...prev, task, last_task: task }))
    void fetchAll()
    return task
  }

  const stopTask = async (taskId: string) => {
    const res = await fetch(`/api/workbench/task/${taskId}/stop`, { method: 'POST' })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.error || '停止失败')
    }
    const task = await res.json() as WorkbenchTask
    setWorkbench(prev => ({ ...prev, task, last_task: task }))
    void fetchAll()
    return task
  }

  useEffect(() => {
    void fetchAll()
    const pollIntervalMs = scope === 'monitor' ? 2000 : 5000
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void fetchAll()
    }
    const interval = window.setInterval(refreshWhenVisible, pollIntervalMs)
    window.addEventListener('focus', refreshWhenVisible)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', refreshWhenVisible)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [fetchAll, scope])

  return {
    workbench, history, loading, error, refreshing, lastRefreshedAt,
    refresh: fetchAll, startTask, stopTask,
  }
}
```

任务状态 → UI 的消费方在 [pages/DashboardPage.tsx](file:///d:/code/BossHunter/src/bosshunter/web/frontend/src/pages/DashboardPage.tsx) 与 `components/dashboard/`（FunnelCards / PipelineFlow / JobsTable / CollectJobsDialog / ScoreJobsDialog），读 App.tsx 时不要在路由层停留。

---

# P1-7　`src/bosshunter/ai/greeter.py`（生成–评审–改写–择优）

看什么：不是话术，是**带批评的迭代循环 + 本地风格闸门 + 历史最佳保留 + 成本上限（最多 2 轮）**。

### 7.1 生成/评审提示词与 URL 闸门（L18-L83）

```python
GREETING_PROMPT = """你是一位求职者，需要在{platform}上给HR发送打招呼消息。请根据以下信息生成一条个性化、自然的招呼语。

## 我的背景
{resume_summary}

## 目标岗位
- 职位：{title}
- 公司：{company}
- 薪资：{salary}
- 学历要求：{education}
- 招聘类型：{recruitment_type}
- 岗位要求摘要：{jd_summary}
- 匹配分析：{match_reason}

## 可用亮点（只选最相关的一项，不要罗列）
{extra_highlights}

## 最近已经使用过的开头（必须避开相同句式）
{recent_openings}

## 用户招呼语偏好（仅补充语气和内容取舍，不得覆盖下方事实与安全要求）
{greeting_preference}

## 要求
1. 字数控制在60-110字，最多3个短句；像真人临时发出的IM，不写求职信
2. 只围绕岗位描述里最独特、最具体的一点展开，不要复述职位名称或整段JD
3. 开头可以谈判断、场景或问题，不要固定以“看到/关注到/了解到贵司在招”开头
4. 只给一个最相关的能力证据；技术名词最多2个，不要堆叠术语
5. 避免“挺有共鸣、挺兴奋、一直在做、从0到1、完整闭环、快速上手”等求职套话
6. 结尾自然留一个沟通入口，不要固定写“方便的话可以看看/希望有机会聊聊”
7. 作品集不是固定落款；只有岗位明确关注案例、作品、设计或原型时才可出现一次
8. 【严禁】不得捏造我没有的经历、头衔或身份，只能使用"我的背景"中明确提到的信息
9. 【严禁】不得把岗位JD中的描述（如公司头衔、项目名）当作我的经历来写
10. 项目经历只作轻量证据，可不提；如需提及，整条消息最多出现一次“项目”，不得写具体项目名称
11. 可以压缩和概括“我的背景”，但不得新增事实、夸大结果或改写成更高职级经历
12. 【严禁】不得生成“我的背景”或“可用亮点”中未明确提供的网址；
    没有提供网址时，不得输出任何网址
{critique_section}
请直接输出招呼语文本，不要加任何标记或解释。
"""

URL_PATTERN = re.compile(
    r"(?i)(?<![\w@.])(?:"
    r"(?:https?://|www\.)[^\s<>()\[\]{}\"'，。！？；]+|"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}(?:[/:?#][^\s<>()\[\]{}\"'，。！？；]+)?"
    r")"
)

REVIEW_PROMPT = """请评估以下{platform}招呼语的质量。

## 岗位
{title} @ {company}

## 招呼语
{greeting}

## 评估维度（每项1-10分）
1. 自然度：是否像真人发的IM消息，而非模板
2. 相关性：是否针对该岗位突出匹配点
3. 差异化：是否能从众多招呼中脱颖而出
4. 克制度：是否只讲一个匹配点，避免项目名、术语堆叠、固定作品集落款和求职套话

请严格按JSON格式输出，不要输出其他内容：
{{"naturalness": 8, "relevance": 7, "differentiation": 6, "restraint": 8, "avg": 7.25, "critique": "改进建议（20字内）"}}
"""
```

### 7.2 迭代主循环（L600-L741 节选）

```python
    review_threshold = ai_cfg.get("greeting_review_threshold", 7.0)
    try:
        max_iterations = max(0, int(ai_cfg.get("greeting_max_iterations", 2) or 0))
    except (TypeError, ValueError):
        max_iterations = 2

    recent_rows = db.execute(
        """
        SELECT greeting
        FROM jobs
        WHERE greeting IS NOT NULL AND trim(greeting) != ''
        ORDER BY updated_at DESC
        LIMIT 20
        """
    ).fetchall()
    recent_openings = [
        opening
        for row in recent_rows
        if (opening := _opening_signature(str(row["greeting"] or "")))
    ]

    # ……
        for index, job in enumerate(jobs, start=1):
            if stop_event is not None and stop_event.is_set():
                break
            best_greeting = None
            pause_after_current = ""

            for iteration in range(max_iterations + 1):
                if stop_event is not None and stop_event.is_set():
                    break
                critique = ""
                if iteration > 0 and best_greeting:
                    try:
                        review = _review_with_token_retry(best_greeting, job, config)
                    except OperationCancelled:
                        cancelled = True
                        break
                    except AIRequestError as exc:
                        if exc.kind == "empty_response":
                            # 质量复核不可用≠生成失败：保留已生成草稿并继续后续岗位（#101 回归）。
                            _notify(
                                config,
                                f"{job['company']}｜{job['title']} 的质量检查未返回内容，已保留可用招呼语并继续。",
                            )
                            break
                        # str(exc) 带 kind/status_code，暂停原因可区分鉴权/限流/额度等类别（issue #101）。
                        pause_after_current = str(exc)
                        break
                    style_issues = _greeting_style_issues(best_greeting, recent_openings)
                    if review is None and not style_issues:
                        _notify(
                            config,
                            f"{job['company']}｜{job['title']} 的质量检查返回格式无法识别，已保留可用招呼语并继续。",
                        )
                        break
                    if review and review.get("avg", 10) >= review_threshold and not style_issues:
                        break
                    critique_parts = style_issues[:]
                    if review and review.get("critique"):
                        critique_parts.append(str(review["critique"]))
                    critique = "；".join(critique_parts)

                try:
                    greeting = _generate_with_token_retry(
                        job, resume_summary, config, critique, recent_openings,
                    )
                except OperationCancelled:
                    cancelled = True
                    break
                except AIRequestError as exc:
                    # str(exc) 带 kind/status_code，暂停原因可区分鉴权/限流/额度等类别（issue #101）。
                    if best_greeting:
                        pause_after_current = str(exc)
                    else:
                        pause_reason = str(exc)
                    break

                if not greeting:
                    if not best_greeting:
                        failed += 1
                    break

                best_greeting = greeting
                if max_iterations == 0:
                    break

            # ……（取消/失败处理略）……

            update_job_greeting(db, job["id"], best_greeting)
            update_job_status(db, job["id"], "ready")
            opening = _opening_signature(best_greeting)
            if opening:
                recent_openings.append(opening)
            count += 1
```

要点：评审分 = LLM 四维分 + 本地确定性 `_greeting_style_issues`（开头签名撞车、套话）双闸门；critique 拼回下一轮 prompt 的 `{critique_section}`；**任一版可用就保留在 best_greeting，复核服务挂了不阻断生成**。

---

# P1-8　`src/bosshunter/ai/resume.py`（生成结果本地确定性审计）

看什么：LLM 产出后，**不花 token 的本地审计层**——新事实（Counter 词频）、新占位符、核心事实丢失、照搬相似度、过程性话术、半句截断；问题清单回填返工 prompt。

### 8.1 审计规则常量（L17-L144 节选）

```python
RESUME_COMPLETION_MARKER = "<!-- BOSSHUNTER_RESUME_DONE -->"
DEFAULT_RESUME_MAX_PAGES = 3
DEFAULT_RESUME_CHARS_PER_PAGE = 1400

RESUME_RETRY_PROMPT = """{base_prompt}

上一次生成结果质量检查未通过，原因如下：
{quality_issues}

请重新生成一版。要求：
1. 必须压缩到 {resume_max_pages} 页以内，正文非空白字符不超过 {resume_max_chars} 个
2. 优先删除弱相关、重复、解释性内容，保留最能支撑岗位JD的真实经历和量化结果
3. 不要新增任何候选人原简历中没有的事实
4. 仍然必须保留基本信息、个人优势、工作经历、教育经历、相关技能
5. 最后一行仍然单独输出 {completion_marker}

请直接输出压缩后的 Markdown 简历正文：
"""

RESUME_ARTIFACT_PHRASES = [
    "以下内容基于", "基于原始简历", "根据原始简历", "根据岗位JD",
    "岗位匹配亮点", "匹配该岗位", "结合岗位要求", "补充说明",
    "原始简历事实", "不虚构", "未虚构", "本次优化", "调整后的简历",
    "定制简历", "以下为优化后的", "针对该岗位", "针对本岗位",
    # ……共 30 个过程性短语……
    "JD逐条对照", "岗位JD覆盖", "逐条对照", "覆盖情况", "匹配说明", "无法覆盖",
]

REQUIRED_RESUME_SECTIONS = [
    "## 基本信息", "## 个人优势", "## 工作经历", "## 教育经历", "## 相关技能",
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{[^{}\n]{1,100}\}\}"),
    re.compile(r"\$\{[^{}\n]{1,100}\}"),
    re.compile(r"\[[^\]\n]{0,80}(?:待填写|待补充|请填写|占位符|placeholder|todo|tbd|xxx)[^\]\n]{0,80}\]", re.I),
    re.compile(r"<[^<>\n]{0,80}(?:待填写|待补充|请填写|占位符|placeholder|todo|tbd|xxx)[^<>\n]{0,80}>", re.I),
    re.compile(r"\b(?:TODO|TBD|XXX)\b", re.I),
    re.compile(r"(?:待填写|待补充|请填写|占位符)(?:[：:][^\s，。；;\n]{0,40})?"),
]

FACT_TOKEN_PATTERNS = [
    re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    re.compile(r"https?://[^\s)>）】]+", re.I),
    re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)(?:19|20)\d{2}(?:[./年-](?:0?[1-9]|1[0-2]))?(?:[./月-](?:0?[1-9]|[12]\d|3[01]))?(?:日)?(?!\d)"),
    re.compile(
        r"(?<![\w.])\d+(?:\.\d+)?(?:\s*[-~至到]\s*\d+(?:\.\d+)?)?\s*"
        r"(?:%|％|年|个月|月|天|人|次|篇|万|亿|元|K|k|W|w|倍|\+)(?!\w)"
    ),
]
```

### 8.2 审计函数（L149-L360）

```python
def _find_resume_artifacts(markdown_text: str) -> list[str]:
    """Find process-disclosure phrases that should not appear in a resume."""
    return [phrase for phrase in RESUME_ARTIFACT_PHRASES if phrase in markdown_text]


def _normalize_validation_token(token: str) -> str:
    return re.sub(r"\s+", "", token).lower()


def _extract_validation_tokens(text: str, patterns: list[re.Pattern]) -> list[str]:
    tokens: list[str] = []
    for pattern in patterns:
        tokens.extend(match.group(0).strip() for match in pattern.finditer(text or ""))
    return tokens


def _find_new_placeholders(markdown_text: str, base_resume: str) -> list[str]:
    """Return placeholders introduced or rewritten by the model.

    Placeholders already present verbatim in the source resume are an accepted
    baseline. Rewording one creates a new token and is therefore blocked.
    """
    base_counts = Counter(
        _normalize_validation_token(token)
        for token in _extract_placeholder_tokens(base_resume)
    )
    seen_counts: Counter[str] = Counter()
    introduced: list[str] = []
    for token in _extract_placeholder_tokens(markdown_text):
        normalized = _normalize_validation_token(token)
        seen_counts[normalized] += 1
        if seen_counts[normalized] > base_counts[normalized] and token not in introduced:
            introduced.append(token)
    return introduced


def _find_new_fact_tokens(markdown_text: str, base_resume: str) -> list[str]:
    """Return fact-sensitive values that do not exist in the source resume."""
    base_tokens = {
        _normalize_validation_token(token)
        for token in _extract_validation_tokens(base_resume, FACT_TOKEN_PATTERNS)
    }
    introduced: list[str] = []
    for token in _extract_validation_tokens(markdown_text, FACT_TOKEN_PATTERNS):
        normalized = _normalize_validation_token(token)
        if normalized not in base_tokens and token not in introduced:
            introduced.append(token)
    return introduced


def _find_missing_core_facts(markdown_text: str, base_resume: str) -> list[str]:
    """Keep fact-like contact/basic-info values from the source resume."""
    source_basic_info = _markdown_section(base_resume, "## 基本信息")
    if not source_basic_info:
        return []
    source_tokens = _extract_validation_tokens(source_basic_info, FACT_TOKEN_PATTERNS)
    generated_keys = {
        _normalize_validation_token(token)
        for token in _extract_validation_tokens(markdown_text, FACT_TOKEN_PATTERNS)
    }
    return [
        token
        for token in source_tokens
        if _normalize_validation_token(token) not in generated_keys
    ]


def _find_blocking_integrity_issues(
    markdown_text: str, base_resume: str,
) -> list[str]:
    """Return issues that must prevent a resume from being marked ready."""
    issues: list[str] = []

    missing_core_facts = _find_missing_core_facts(markdown_text, base_resume)
    if missing_core_facts:
        issues.append(
            "事实完整性校验失败：缺少基础简历中的关键信息："
            + ", ".join(missing_core_facts[:8])
        )

    new_facts = _find_new_fact_tokens(markdown_text, base_resume)
    if new_facts:
        issues.append(
            "事实完整性校验失败：模型新增了原始简历中不存在的数据："
            + ", ".join(new_facts[:8])
        )

    new_placeholders = _find_new_placeholders(markdown_text, base_resume)
    if new_placeholders:
        issues.append(
            "占位符校验失败：模型新增或改写了占位符："
            + ", ".join(new_placeholders[:8])
        )
    return issues


def _strip_completion_marker(markdown_text: str) -> tuple[str | None, str | None]:
    """Return any non-empty resume body, removing the optional completion marker."""
    marker_issue = None
    if RESUME_COMPLETION_MARKER not in markdown_text:
        marker_issue = "生成结果缺少完成标记，可能不完整"
    body = markdown_text.split(RESUME_COMPLETION_MARKER, 1)[0].strip()
    if not body:
        return None, "生成结果为空"
    return f"{body}\n", marker_issue


def _find_resume_quality_issues(
    markdown_text: str, base_resume: str,
    job: dict | None = None, max_chars: int | None = None,
    max_pages: int = DEFAULT_RESUME_MAX_PAGES,
) -> list[str]:
    """Find issues that make a generated resume unsafe to mark as ready."""
    issues: list[str] = []
    stripped = markdown_text.strip()

    if not stripped.startswith("#"):
        issues.append("生成结果不像 Markdown 简历正文")

    if max_chars and _resume_content_length(markdown_text) > max_chars:
        issues.append(f"简历内容过长，默认应控制在 {max_pages} 页以内")

    for section in _required_sections_from_base(base_resume):
        if section not in markdown_text:
            issues.append(f"缺少基础简历中的常规栏目：{section.replace('## ', '')}")

    last_line = _last_content_line(markdown_text)
    if _looks_abrupt(last_line):
        issues.append("简历末尾疑似半句截断")

    if _is_nearly_unchanged(markdown_text, base_resume):
        issues.append("生成结果与原始简历几乎一致，定制化不足")

    if job:
        job_text = " ".join(str(job.get(key) or "") for key in ("title", "company", "company_industry", "jd"))
        for group in ROLE_KEYWORD_GROUPS:
            if any(token in job_text for token in group["triggers"]):
                if not any(token in markdown_text for token in group["required"]):
                    issues.append(f"未体现岗位关键词方向：{group['name']}")

    return issues


def _looks_abrupt(line: str) -> bool:
    if not line:
        return True
    if line.startswith("#"):
        return True
    if len(line) < 12:
        return True
    if line[-1] in "。.!！?？；;)）]】》\"'”’":
        return False
    if re.search(r"(，|、|及|和|与|围绕|包括|病例|技术|项目)$", line):
        return True
    return False


def _is_nearly_unchanged(markdown_text: str, base_resume: str) -> bool:
    base = _normalize_resume_for_similarity(base_resume)
    tailored = _normalize_resume_for_similarity(markdown_text)
    if len(base) < 500 or len(tailored) < 500:
        return False
    return SequenceMatcher(None, base, tailored).ratio() >= 0.985


def _normalize_resume_for_similarity(text: str) -> str:
    return re.sub(r"\s+", "", text)
```

迁移到创想∞的对应思路：市场分析 Agent 产出后，确定性校验「数字必须带来源引用 / 假设必须有标记 / TAM-SAM-SOM 齐备」，不通过带原因返工——同一模式。

---

# P1-9　Collection：协议 / 契约 / 能力矩阵 / 注册器 / 编排器

看什么：插件契约（Protocol + hooks）、平台无关数据契约、新平台默认只读的能力矩阵、Registry、单平台登录墙不连坐。

### 9.1 协议与失败分类（`collection/base.py` 全文）

```python
"""Collector protocol and explicit platform failure categories."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable, Protocol

from bosshunter.collection.models import (
    JobCandidate,
    PlatformCollectionRequest,
    PlatformCollectionResult,
)


class CollectionError(RuntimeError):
    """An expected, user-actionable collection failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CollectionBlockedError(CollectionError):
    """The platform requires user action or has blocked the session."""


@dataclass
class CollectorHooks:
    """Callbacks supplied by the shared collection layer."""

    stop_event: Event | None
    on_list_candidate: Callable[[JobCandidate], bool]
    on_candidate: Callable[[JobCandidate], bool]
    on_parse_failed: Callable[[str], None]
    on_event: Callable[..., None]


class Collector(Protocol):
    platform: str

    def collect(
        self,
        request: PlatformCollectionRequest,
        hooks: CollectorHooks,
    ) -> PlatformCollectionResult:
        ...
```

### 9.2 平台无关数据契约（`collection/models.py` L29-L90 节选）

```python
@dataclass(frozen=True)
class PlatformCollectionRequest:
    platform: PlatformId
    keywords: list[str]
    cities: list[str]
    city_codes: dict[str, str]
    max_pages: int = 3
    sort: str = "default"
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobCandidate:
    """A platform-neutral job candidate emitted by a collector."""

    platform: PlatformId
    source_job_id: str
    title: str
    company: str
    salary: str = ""
    city: str = ""
    city_code: str = ""
    experience: str = ""
    education: str = ""
    recruitment_type: str = "unknown"
    jd: str = ""
    hr_name: str = ""
    hr_title: str = ""
    hr_active: str = ""
    company_size: str = ""
    company_industry: str = ""
    url: str = ""
    source_keyword: str = ""

    @property
    def storage_id(self) -> str:
        if self.platform != "boss":
            return f"{self.platform}:{self.source_job_id}"
        return self.source_job_id

    def as_job_record(self) -> dict[str, Any]:
        return {
            "id": self.storage_id,
            "title": self.title,
            "company": self.company,
            # ……平台字段统一映射到 jobs 表行；recruitment_type 兜底用
            # classify_recruitment_type(title, experience, jd) 保守推断……
            "jd": clean_job_description(self.jd),
            # ……
        }
```

### 9.3 能力矩阵（`collection/capabilities.py` 全文）

```python
"""Server-side capability boundaries for platform-specific workflows."""

PLATFORM_CAPABILITIES: dict[str, frozenset[str]] = {
    "boss": frozenset({"collect", "score", "greet", "deliver", "monitor"}),
    # New platforms start read-only. Delivery and monitoring stay locked until
    # an authorized real-account acceptance test has verified the live DOM and
    # the maintainer explicitly enables those capabilities in a later change.
    "zhilian": frozenset({"collect", "score", "greet"}),
    "51job": frozenset({"collect", "score", "greet"}),
    "liepin": frozenset({"collect", "score", "greet"}),
}


def platform_supports(platform: str, capability: str) -> bool:
    return capability in PLATFORM_CAPABILITIES.get(str(platform), frozenset())
```

### 9.4 注册器（`collection/registry.py` 全文）

```python
"""Platform collector registry."""

from __future__ import annotations

from collections.abc import Callable

from bosshunter.collection.base import Collector


class CollectorRegistry:
    def __init__(self, factories: dict[str, Callable[[], Collector]] | None = None):
        self._factories = dict(factories or {})

    def register(self, platform: str, factory: Callable[[], Collector]) -> None:
        self._factories[str(platform)] = factory

    def get(self, platform: str) -> Collector:
        try:
            return self._factories[platform]()
        except KeyError as exc:
            raise ValueError(f"未注册的采集平台：{platform}") from exc

    def platforms(self) -> tuple[str, ...]:
        return tuple(self._factories)
```

### 9.5 共享处理器（去重/过滤/入库下沉）与串行编排（orchestrator.py L207-L429 节选）

```python
class _SharedProcessor:
    def __init__(
        self, conn, request: PlatformCollectionRequest, *,
        run_id: str, platform_index: int, platform_total: int,
        stop_event: Event | None, config: dict[str, Any],
        emit: Callable[[CollectionProgress], None],
    ):
        # ……
        self.new_job_ids: list[str] = []

    def inspect(self, candidate: JobCandidate) -> bool:
        self.progress.seen += 1
        if job_identity_exists(
            self.conn, candidate.platform, candidate.source_job_id,
            legacy_job_id=candidate.storage_id,
        ):
            self.progress.duplicate += 1
            self.event()
            return False
        profile = self.config.get("profile", {}) if isinstance(self.config.get("profile"), dict) else {}
        if matching_deal_breaker(candidate.title, profile.get("deal_breakers") or []):
            self.progress.filtered += 1
            self.event(message="职位名命中过滤规则")
            return False
        if matching_blocked_company(candidate.company, profile.get("blocked_companies") or []):
            self.progress.filtered += 1
            self.event(message="公司命中过滤规则")
            return False
        self.event()
        return True

    def save(self, candidate: JobCandidate) -> bool:
        profile = self.config.get("profile", {}) if isinstance(self.config.get("profile"), dict) else {}
        if matching_deal_breaker(candidate.jd, profile.get("jd_deal_breakers") or []):
            self.progress.filtered += 1
            self.event(message="JD 命中过滤规则")
            return True
        try:
            inserted = insert_job_if_new(self.conn, candidate.as_job_record())
        except Exception as exc:
            self.progress.save_failed += 1
            self.event(message=f"保存岗位失败：{type(exc).__name__}")
            return True
        if inserted:
            self.new_job_ids.append(candidate.storage_id)
        else:
            self.progress.duplicate += 1
        self.event(phase="saving")
        if self.stop_event is not None and self.stop_event.is_set():
            return False
        return self.stop_event is None or not self.stop_event.is_set()
```

```python
class CollectionOrchestrator:
    """Run selected platform collectors one after another in the given order."""

    def __init__(self, config, *, db_path=None, registry=None, run_id=None, task_id=""):
        # ……
        self.registry = registry or CollectorRegistry({
            "boss": BossCollector,
            "zhilian": ZhilianCollector,
            "51job": Job51Collector,
            "liepin": LiepinCollector,
        })
        # ……

    def run(self, raw_options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = normalize_collection_options(self.config, raw_options)
        order = options["platform_order"]
        states: dict[str, dict[str, Any]] = {
            platform: {"status": "queued", "new": 0, "target": None, "percent": None}
            for platform in order
        }
        create_collection_run(self.db_path, run_id=self.run_id, task_id=self.task_id,
                              options=options, platform_states=states)
        all_new_ids: list[str] = []
        platform_results: list[PlatformCollectionResult] = []
        conn = get_db(self.db_path)
        try:
            for index, platform in enumerate(order, start=1):
                if self.stop_event is not None and self.stop_event.is_set():
                    states[platform]["status"] = "stopped"
                    states[platform]["reason_code"] = "user_stopped"
                    break
                raw = options["platforms"][platform]
                request = PlatformCollectionRequest(platform=platform, **raw)
                states[platform]["status"] = "running"
                self._persist(states, all_new_ids, platform)
                processor = _SharedProcessor(
                    conn, request, run_id=self.run_id, platform_index=index,
                    platform_total=len(order), stop_event=self.stop_event,
                    config=self.config, emit=lambda *a, **k: None,
                )
                processor.emit = lambda progress, p=platform, processor_ref=processor: self._emit(
                    states, p, progress, all_new_ids, processor_ref.new_job_ids
                )
                hooks = CollectorHooks(
                    stop_event=self.stop_event,
                    on_list_candidate=processor.inspect,
                    on_candidate=processor.save,
                    on_parse_failed=lambda reason, p=processor: self._parse_failed(p, reason),
                    on_event=lambda p=processor, **kwargs: p.event(**kwargs),
                )
                try:
                    collector = (
                        BossCollector(config=self.config, safety_conn=conn)
                        if platform == "boss" and self._uses_default_registry
                        else Job51Collector(config=self.config, safety_conn=conn)
                        if platform == "51job" and self._uses_default_registry
                        else ZhilianCollector(config=self.config, safety_conn=conn)
                        if platform == "zhilian" and self._uses_default_registry
                        else self.registry.get(platform)
                    )
                    result = collector.collect(request, hooks)
                except CollectionError as exc:
                    result = PlatformCollectionResult(platform, "blocked", exc.code, exc.message, error=str(exc))
                except Exception as exc:
                    result = PlatformCollectionResult(platform, "failed", "network_error",
                                                      f"{platform} 采集失败", error=str(exc)[:500])
                result.new_job_ids = list(processor.new_job_ids)
                result.counts = self._counts(processor.progress)
                platform_results.append(result)
                states[platform].update({
                    "status": result.status, "new": len(result.new_job_ids),
                    # ……计数与原因码落 states……
                    "reason_code": result.reason_code, "message": result.message,
                })
                all_new_ids.extend(result.new_job_ids)
                self._persist(states, all_new_ids, platform,
                              stop_reason=result.reason_code, error=result.error)
                # A login wall belongs to the current recruitment platform:
                # keep its blocked result but let independent later platforms
                # continue. Other unknown/risk blocks remain queue-wide until
                # they have an equally explicit platform-local classification.
                if (
                    (result.status == "blocked" and result.reason_code != "login_required")
                    or result.reason_code in {"user_stopped", "browser_disconnected"}
                    or (self.stop_event and self.stop_event.is_set())
                ):
                    break
        finally:
            conn.close()

        unique_new_ids = list(dict.fromkeys(str(job_id) for job_id in all_new_ids if str(job_id)))
        stopped = bool(self.stop_event and self.stop_event.is_set()) or any(
            r.reason_code == "user_stopped" for r in platform_results)
        errors = any(r.status in {"blocked", "failed"} for r in platform_results)
        shortages = any(r.status == "completed_with_shortage" for r in platform_results)
        outcome = ("stopped" if stopped else "completed_with_errors" if errors
                   else "completed_with_shortage" if shortages else "completed")
        if options["auto_score"] and unique_new_ids and not stopped:
            try:
                self._emit_scoring(states, unique_new_ids)
                from bosshunter.ai.scorer import score_jobs

                score_config = dict(self.config)
                score_config["_workbench_stop_event"] = self.stop_event
                score_jobs(score_config, scope="selected", job_ids=unique_new_ids,
                           limit=None, force_rescore=False)
            except Exception as exc:
                outcome = "completed_with_errors"
                self._persist(states, unique_new_ids, "",
                              error=f"自动评分失败：{str(exc)[:500]}")
        self._persist(states, unique_new_ids, "", status=outcome,
                      stop_reason="user_stopped" if stopped else "")
        return {
            "run_id": self.run_id,
            "status": outcome,
            "platforms": states,
            "collected_job_ids": unique_new_ids,
            "results": [result.__dict__ for result in platform_results],
        }
```

**故障隔离的关键就是 L396-L401 那个条件**：`blocked + login_required` 只终止当前平台、继续队列；其它 blocked（验证码/拦截）和断连/用户停止才终止全队列。

---

# P1-10　`tests/`（重点看失败路径测试，不看数字）

44 个测试文件 / 608 项测试。先精读下面这一份（它同时覆盖了：断点保留、用户停止与故障暂停的记录差异、重启接管、可恢复 run 与回收站冲突——是状态机测试范本），再按 10.2 的清单选读。

### 10.1 `tests/test_scoring_recovery.py`（全文）

```python
from threading import Event
from unittest.mock import patch

import pytest

from bosshunter.ai.scorer import ScoreOutcome, score_jobs
from bosshunter.db import (
	JobDeletionConflictError,
	get_db,
	insert_job,
	soft_delete_jobs,
	update_job_score,
	update_job_status,
)
from bosshunter.scoring_run_store import (
	create_scoring_run,
	get_scoring_run,
	mark_orphaned_scoring_runs_paused,
	update_scoring_run,
)
from bosshunter.scoring_selection import preview_scoring, select_scoring_jobs, validate_options


def _job(job_id: str) -> dict:
	return {
		"id": job_id,
		"title": f"AI Product Manager {job_id}",
		"company": "Example",
		"salary": "20-30K",
		"city": "Shanghai",
		"experience": "1-3 years",
		"jd": "Build AI product features",
		"hr_name": "HR",
		"hr_title": "Recruiter",
		"hr_active": "active",
		"company_size": "100-499",
		"company_industry": "Software",
		"url": f"https://example.com/jobs/{job_id}",
	}


def test_default_selection_scores_all_unscored_pending_but_never_historical_or_deleted(tmp_path):
	db = get_db(tmp_path / "selection.db")
	try:
		for job_id in ("old-pending", "new-pending", "already-scored", "deleted-pending"):
			insert_job(db, _job(job_id))
		update_job_score(db, "already-scored", 82, "already evaluated")
		update_job_status(db, "already-scored", "ready")
		soft_delete_jobs(db, ["deleted-pending"], confirmed=True)

		selected = select_scoring_jobs(db)
		preview = preview_scoring(db)
	finally:
		db.close()

	assert {job["id"] for job in selected} == {"old-pending", "new-pending"}
	assert preview["eligible_jobs"] == 2
	assert preview["job_ids"] and len(preview["job_ids"]) == 2


def test_selected_jobs_do_not_rescore_existing_results_without_explicit_force(tmp_path):
	db = get_db(tmp_path / "force.db")
	try:
		for job_id in ("pending", "scored"):
			insert_job(db, _job(job_id))
		update_job_score(db, "scored", 75, "evaluated")
		update_job_status(db, "scored", "scored")

		normal = select_scoring_jobs(db, scope="selected", job_ids=["pending", "scored"])
		forced = select_scoring_jobs(
			db,
			scope="selected",
			job_ids=["pending", "scored"],
			force_rescore=True,
		)
	finally:
		db.close()

	assert [job["id"] for job in normal] == ["pending"]
	assert {job["id"] for job in forced} == {"pending", "scored"}


def test_scoring_selection_rejects_non_array_job_ids():
	with pytest.raises(ValueError, match="岗位 ID 必须是数组"):
		validate_options(scope="selected", job_ids="job-one")


def test_pause_checkpoint_keeps_current_and_unstarted_jobs_for_recovery(tmp_path):
	db_path = tmp_path / "checkpoint.db"
	db = get_db(db_path)
	try:
		for job_id in ("one", "two", "three"):
			insert_job(db, _job(job_id))
	finally:
		db.close()

	checkpoints: list[dict] = []
	outcomes = [
		ScoreOutcome(failure_detail="temporary invalid response"),
		ScoreOutcome(pause_reason="AI quota exhausted"),
	]
	with (
		patch("bosshunter.ai.scorer.get_db", side_effect=lambda: get_db(db_path)),
		patch("bosshunter.ai.scorer._load_resume", return_value="real resume"),
		patch("bosshunter.ai.scorer.quick_score", return_value=(80, "pass")),
		patch("bosshunter.ai.scorer._score_job_with_ai", side_effect=outcomes),
	):
		score_jobs(
			{
				"ai": {"scoring_concurrency": 1},
				"scoring": {"threshold": 60},
				"_workbench_score_checkpoint": checkpoints.append,
			}
		)

	assert checkpoints[-1]["status"] == "paused"
	assert checkpoints[-1]["pause_reason"] == "AI quota exhausted"
	assert checkpoints[-1]["error"] == "AI quota exhausted"
	assert len(checkpoints[-1]["remaining_job_ids"]) == 2
	assert set(checkpoints[-1]["remaining_job_ids"]).issubset({"one", "two", "three"})


def test_user_stop_pause_keeps_error_empty_for_clean_record(tmp_path):
	db_path = tmp_path / "userstop.db"
	db = get_db(db_path)
	try:
		for job_id in ("one", "two"):
			insert_job(db, _job(job_id))
	finally:
		db.close()

	checkpoints: list[dict] = []
	stop_event = Event()
	stop_event.set()
	with (
		patch("bosshunter.ai.scorer.get_db", side_effect=lambda: get_db(db_path)),
		patch("bosshunter.ai.scorer._load_resume", return_value="real resume"),
		patch("bosshunter.ai.scorer.quick_score", return_value=(80, "pass")),
	):
		score_jobs(
			{
				"ai": {"scoring_concurrency": 1},
				"scoring": {"threshold": 60},
				"_workbench_stop_event": stop_event,
				"_workbench_score_checkpoint": checkpoints.append,
			}
		)

	assert checkpoints[-1]["status"] == "paused"
	assert checkpoints[-1]["pause_reason"] == "用户暂停或任务中断"
	assert checkpoints[-1]["error"] == ""


def test_restart_preserves_remaining_jobs_and_marks_run_recoverable(tmp_path):
	db_path = tmp_path / "restart.db"
	get_db(db_path).close()
	create_scoring_run(
		db_path,
		run_id="run-restart",
		options={"scope": "pending", "limit": None, "force_rescore": False},
		job_ids=["one", "two"],
	)
	update_scoring_run(
		db_path,
		"run-restart",
		status="running",
		remaining_job_ids=["two"],
	)

	assert mark_orphaned_scoring_runs_paused(db_path) == 1
	run = get_scoring_run(db_path, "run-restart")

	assert run is not None
	assert run["status"] == "paused"
	assert run["remaining_job_ids"] == ["two"]
	assert run["recoverable"] is True


def test_recycle_bin_cannot_remove_jobs_referenced_by_recoverable_scoring_run(tmp_path):
	db_path = tmp_path / "conflict.db"
	db = get_db(db_path)
	try:
		insert_job(db, _job("in-flight"))
	finally:
		db.close()
	create_scoring_run(
		db_path,
		run_id="run-conflict",
		options={"scope": "pending", "limit": None, "force_rescore": False},
		job_ids=["in-flight"],
	)
	update_scoring_run(db_path, "run-conflict", status="paused")

	db = get_db(db_path)
	try:
		with pytest.raises(JobDeletionConflictError):
			soft_delete_jobs(db, ["in-flight"], confirmed=True)
	finally:
		db.close()

	update_scoring_run(db_path, "run-conflict", status="stopped", remaining_job_ids=[])
	db = get_db(db_path)
	try:
		result = soft_delete_jobs(db, ["in-flight"], confirmed=True)
	finally:
		db.close()
	assert result["affected_count"] == 1
```

### 10.2 其余测试选读清单（按主题）

| 主题 | 文件 | 学什么 |
|---|---|---|
| LLM 容错 | tests/test_ai_services.py、test_ai_token_resilience.py、test_ai_credentials.py | 如何 mock 各家异常；截断/空响应/限流分支构造 |
| 编排与隔离 | test_collection_orchestrator.py、test_collector_registry.py、test_capabilities.py、test_collection_safety.py、test_collection_runs.py、test_run_store_boundaries.py | 单平台故障不连坐、注册表边界、run 存储边界 |
| 任务/取消 | test_cancellation.py、test_web_api_routes.py、test_web_preflight.py | 协作式取消、API 路由、开跑预检 |
| 安全/投递 | test_platform_delivery_guard.py、test_monitor_safety.py、test_manual_external_sent.py、test_recycle_bin.py | 能力守卫、安全锁、人工回填、回收站保护 |
| 简历 | test_resume_pdf_runtime.py、test_resume_upload_safety.py | 文件/编码/安全边界 |
| 浏览器 | test_browser_facade.py、test_browser_runtime.py、test_browser_diagnostics.py | 重依赖如何通过外观层（facade）mock 成可测 |

读法：mock 的 seam 在哪（注意全部是 `_workbench_*` config 私有键 + `patch` 模块级函数）、失败用例如何命名（`test_<场景>_<期望>`）、每个状态机跳转是否正反两条用例。

---

# P2　暂不深入（业务相关性低，知道结论即可）

| 文件 | 不深读原因 | 需要时回查 |
|---|---|---|
| browser/runtime/cdp-proxy.mjs | CDP/WebSocket 桥，无浏览器场景 | 本地运行时端点设计 |
| browser/client.py | 同上 | 全超时、异常返 None 的容错客户端写法 |
| executor/sender.py | BOSS 弹窗/送达验证强耦合 | 双通道验证+稳定性复读+防重的事务化思想 |
| throttle.py | 拟人化反检测专用 | 高斯随机间隔（与我们无关） |
| platform_safety.py | 平台账号安全锁 | 「开页前预订预算 + 持久锁」可改造为 LLM 成本预算守卫 |
| collection/platforms/job51.py | 采样/风控是爬虫战场 | fail-closed 注释论证方式 |

红线：平台风控、反检测、拟人化操作不进入创想∞技术路线。

---

# 附：BossHunter → 创想∞ 技术迁移表

> 读完代码后逐行填「证据（函数+行号）」，判定只用 ✅ 立即迁移 / ◐ 试点借鉴 / ❌ 不迁移。

| BossHunter 实现 | 创想∞现状 | 判定 | 怎么迁 |
|---|---|---|---|
| 8 类错误归一 + 差异化重试（normalize_ai_error / _request_score） | LLMClient 仅空正文重试 | ✅ | 改造 LLMClient：错误分类 + 重试策略矩阵，12 Agent 共用 |
| 结构化输出 + 程序校验闸门（_structured_score_result） | AgentResult 无校验 | ✅ | AgentResult 增加 Schema Validator，不合法不进下游 |
| 临界结论独立二评（_score_job_with_ai / _merge_review_results） | Agent 单次执行 | ◐ | 仅高风险结论（投入/放弃）加 Review 节点，限临界区间控成本 |
| Run/Checkpoint 持久化（scoring_runs + run store + orphan 接管） | reports/ 文件，无 Run | ✅ | 增加 Run/Checkpoint 表与启动时僵死任务接管 |
| WorkbenchTask 状态机 + Runner + stop Event | Streamlit rerun | ✅ | Task 状态机（running/stopping/paused/终态）+ 单任务守卫 |
| Registry + Capability 矩阵 | agent_name 硬编码分支 | ✅ | AgentRegistry.register + Agent 能力/依赖声明，高风险动作默认只读 |
| 本地确定性结果审计（resume.py 审计函数组） | 基本没有 | ✅ | ResultValidator：来源数字、假设标记、必备章节，带原因返工 |
| 生成–评审–改写择优（greeter 迭代循环） | 红队/评审单次链路 | ◐ | 选 1–2 个高风险 Agent 试点 Critic/Repair，限 2 轮 |
| 部分成功语义（单条失败不连坐） | 任一 Agent 失败影响全局 | ✅ | Agent 级失败隔离 + 失败清单 + outcome 分级 |
| 无迁移工具幂等表迁移（_migrate_v*） | 未定型 | ◐ | 若用 SQLite 持久化，直接采用同模式 |
| 前端可见性轮询/状态映射（useDashboard） | Streamlit 自动重跑 | ◐ | 产品化前端阶段借鉴轮询、防重入、禁用态 |
| 失败路径优先的测试组织 | 测试薄弱 | ✅ | 先补「Agent 坏结构/超时/中断恢复」三类测试 |
| 复杂浏览器自动化/反检测 | 不相关 | ❌ | 不迁移 |

建议重构顺序：**LLMClient 错误层 → ResultValidator → Run/Checkpoint → TaskRunner → AgentRegistry**。
