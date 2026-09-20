# -*- coding: utf-8 -*-
"""LLM 错误归一化与差异化重试策略（Phase 7-5，借鉴 BossHunter credentials.py）。

把各厂商千奇百怪的报错收敛为有限的错误类别，上层执行器据此决定：
当前 Agent 重试 / 退避 / 提升 token / 整条 Run 暂停，而不是统一 try-except-retry。
"""
from __future__ import annotations

from typing import Optional


# ── 错误类别（建议.md 第七节定义的 8 类 + 网络/未知兜底） ──
class LLMErrorKind:
    AUTH = "auth"                         # API Key 无效/无权限 → Run 失败
    RATE_LIMIT = "rate_limit"             # 触发频率限制 → 退避后重试
    QUOTA = "quota"                       # 额度/余额不足 → Run 暂停
    TIMEOUT = "timeout"                   # 请求超时 → 有限重试
    CONTEXT_LIMIT = "context_limit"       # 输入超长 → 当前 Agent 失败（需压缩上下文）
    OUTPUT_LIMIT = "output_limit"         # 模型不接受 max_tokens 设置 → 调整后重试
    OUTPUT_TRUNCATED = "output_truncated" # 输出被截断 → 翻倍 max_tokens 重试
    EMPTY_RESPONSE = "empty_response"     # 空正文（推理占满等）→ 提升 token 重试
    NETWORK = "network"                   # 连接类故障 → 有限重试
    UNKNOWN = "unknown"


class LLMRequestError(RuntimeError):
    """归一化后的 LLM 请求失败，不携带 Key 等敏感信息。"""

    def __init__(self, kind: str, user_message: str, status_code: Optional[int] = None):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code

    def __str__(self) -> str:
        suffix = f" ({self.kind}" + (f", status={self.status_code}" if self.status_code else "") + ")"
        return self.user_message + suffix


# ── 错误关键词（判定顺序参考 BossHunter：状态码优先，额度先于限流，限流先于上下文） ──
_QUOTA_MARKERS = (
    "insufficient_quota", "quota exceeded", "token quota", "billing", "balance",
    "credit", "budget", "overdue", "payment required", "余额不足", "额度不足", "欠费",
)
_RATE_MARKERS = (
    "rate limit", "too many requests", "requests per minute", "tokens per minute",
    " tpm", " rpm", "限流", "频率限制", "请求过于频繁",
)
_CONTEXT_MARKERS = (
    "context_length", "context length", "maximum context", "max context",
    "input tokens", "prompt tokens", "too many tokens", "prompt is too long",
    "request too large", "上下文", "输入过长", "context length exceeded",
)
_OUTPUT_LIMIT_MARKERS = (
    "max_tokens", "max completion tokens", "maximum output tokens", "tokens to sample",
)
_AUTH_MARKERS = (
    "invalid api key", "authentication", "permission denied", "unauthorized",
    "invalid authentication", "api-key", "鉴权", "密钥无效",
)
_TIMEOUT_MARKERS = ("timeout", "timed out", "readtimeout", "连接超时", "请求超时")


def _extract_status_code(exc: Exception, response: object = None) -> Optional[int]:
    resolved = response if response is not None else getattr(exc, "response", None)
    code = getattr(exc, "status_code", None) or getattr(resolved, "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def _response_error_detail(response: object) -> str:
    """尽力提取错误体文本，任何异常都吞掉，归一化本身不能再抛错。"""
    if response is None:
        return ""
    for attr in ("text", "content"):
        val = getattr(response, attr, None)
        if isinstance(val, str):
            return val
        if isinstance(val, bytes):
            try:
                return val.decode("utf-8", errors="ignore")
            except Exception:
                return ""
    return ""


def normalize_llm_error(exc: Exception, response: object = None) -> LLMRequestError:
    """把厂商异常分类为 LLMErrorKind。已是 LLMRequestError 的直接返回。"""
    if isinstance(exc, LLMRequestError):
        return exc

    status_code = _extract_status_code(exc, response)
    raw = f"{type(exc).__name__} {exc} {_response_error_detail(response)}".lower()

    # 判定顺序：401/403 明确鉴权 → 额度（可配 402 或关键词）→ 429 限流
    # → 上下文 → 输出上限 → 超时 → 网络。顺序不可随意调换：真实错误体常混排
    # 多种提示（如"余额不足，请缩短输入"），先查上下文会把额度问题误分类。
    if status_code in {401, 403} or any(m in raw for m in _AUTH_MARKERS):
        return LLMRequestError(LLMErrorKind.AUTH, "AI API Key 无效或当前模型没有访问权限", status_code)
    if status_code == 402 or any(m in raw for m in _QUOTA_MARKERS):
        return LLMRequestError(LLMErrorKind.QUOTA, "AI Token 额度或账户余额不足", status_code)
    if status_code == 429 or any(m in raw for m in _RATE_MARKERS):
        return LLMRequestError(LLMErrorKind.RATE_LIMIT, "AI 服务触发请求或 Token 频率限制", status_code)
    # 5xx 服务端故障：可重试的服务侧错误，归 NETWORK（不当作 UNKNOWN 黑盒）
    if status_code and 500 <= status_code < 600:
        return LLMRequestError(LLMErrorKind.NETWORK, f"AI 服务端故障（HTTP {status_code}），可稍后重试", status_code)
    if any(m in raw for m in _CONTEXT_MARKERS):
        return LLMRequestError(LLMErrorKind.CONTEXT_LIMIT, "请求内容超过当前模型的上下文限制", status_code)
    if any(m in raw for m in _OUTPUT_LIMIT_MARKERS):
        return LLMRequestError(LLMErrorKind.OUTPUT_LIMIT,
                               "当前模型不接受设置的输出 Token 上限", status_code)
    if any(m in raw for m in _TIMEOUT_MARKERS):
        return LLMRequestError(LLMErrorKind.TIMEOUT, "AI 服务请求超时", status_code)

    # openai/httpx 系连接异常
    module = type(exc).__module__ or ""
    name = type(exc).__name__ or ""
    if "timeout" in name.lower() or any(m in raw for m in _TIMEOUT_MARKERS):
        return LLMRequestError(LLMErrorKind.TIMEOUT, "AI 服务请求超时", status_code)
    if "connection" in raw or "network" in raw or "unreachable" in raw or "remote end closed" in raw \
            or module.startswith(("httpx", "httpcore", "urllib3", "requests")):
        return LLMRequestError(LLMErrorKind.NETWORK, "AI 服务连接失败", status_code)
    return LLMRequestError(LLMErrorKind.UNKNOWN, f"AI 服务请求失败：{name}", status_code)


# ── 差异化重试策略 ──
class ErrorAction:
    RETRY = "retry"            # 立即/退避后重试当前 Agent
    RAISE = "raise"            # 不可恢复：当前 Agent 失败
    PAUSE_RUN = "pause_run"    # 服务级故障：整条 Run 暂停保进度
    FAIL_RUN = "fail_run"      # 鉴权等配置错误：整条 Run 失败


# 各错误类别的基础策略
_POLICY: dict[str, tuple[str, int]] = {
    # kind: (动作, 最大尝试次数)
    LLMErrorKind.EMPTY_RESPONSE:  (ErrorAction.RETRY, 3),
    LLMErrorKind.OUTPUT_TRUNCATED:(ErrorAction.RETRY, 2),
    LLMErrorKind.OUTPUT_LIMIT:    (ErrorAction.RETRY, 2),
    LLMErrorKind.RATE_LIMIT:      (ErrorAction.RETRY, 4),
    LLMErrorKind.TIMEOUT:         (ErrorAction.RETRY, 3),
    LLMErrorKind.NETWORK:         (ErrorAction.RETRY, 3),
    LLMErrorKind.CONTEXT_LIMIT:   (ErrorAction.RAISE, 1),   # 由执行器决定是否压缩上下文
    LLMErrorKind.QUOTA:           (ErrorAction.PAUSE_RUN, 1),
    LLMErrorKind.AUTH:            (ErrorAction.FAIL_RUN, 1),
    LLMErrorKind.UNKNOWN:         (ErrorAction.RETRY, 2),
}


class RetryPolicy:
    """根据错误类别决定动作、尝试次数与退避秒数。"""

    def action_for(self, kind: str) -> str:
        return _POLICY.get(kind, (ErrorAction.RETRY, 2))[0]

    def max_attempts_for(self, kind: str) -> int:
        return _POLICY.get(kind, (ErrorAction.RETRY, 2))[1]

    def can_retry(self, kind: str, attempt: int) -> bool:
        """attempt 从 1 开始（1 表示首次调用已经失败）。"""
        action, max_attempts = _POLICY.get(kind, (ErrorAction.RETRY, 2))
        return action == ErrorAction.RETRY and attempt < max_attempts

    @staticmethod
    def backoff_seconds(kind: str, attempt: int) -> float:
        """指数退避：限流 2/4/8/16s 封顶 30s；网络/超时 1/2/4s。"""
        if kind == LLMErrorKind.RATE_LIMIT:
            return min(2.0 * (2 ** max(0, attempt - 1)), 30.0)
        if kind in (LLMErrorKind.NETWORK, LLMErrorKind.TIMEOUT):
            return min(1.0 * (2 ** max(0, attempt - 1)), 10.0)
        return 0.5


# 全局限速：所有平台共享（DeepSeek 并发 7 路时尤其需要）
GLOBAL_RETRY_POLICY = RetryPolicy()
