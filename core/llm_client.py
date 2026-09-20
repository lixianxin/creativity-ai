# -*- coding: utf-8 -*-
"""统一 LLM 客户端（Phase 7-5 加固）。

职责：
1. 多平台探活与故障切换（DeepSeek 主，百炼/智谱备）；
2. 所有异常经 normalize_llm_error 归一为 LLMErrorKind；
3. 按 RetryPolicy 做差异化处理：
   - EMPTY_RESPONSE / OUTPUT_TRUNCATED → 提升 token 预算重试；
   - RATE_LIMIT / TIMEOUT / NETWORK    → 指数退避重试，并尝试切换备用平台；
   - CONTEXT_LIMIT                    → 抛出（由执行器决定是否压缩上下文）；
   - QUOTA                            → 抛出，执行器暂停整条 Run 保进度；
   - AUTH                             → 抛出，整条 Run 失败。
"""
import time
from typing import Optional, Set

from openai import OpenAI

from core.config import PLATFORMS, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT
from core.llm_errors import (
    LLMErrorKind,
    LLMRequestError,
    normalize_llm_error,
    GLOBAL_RETRY_POLICY,
)

# 总尝试次数硬上限（含平台切换），防止任何分类失误导致死循环
_HARD_ATTEMPT_CAP = 8
_TOKEN_HARD_CAP = 65536


class LLMClient:
    """单例式 LLM 调用器。首次调用时自动探活选择可用平台。"""

    def __init__(self):
        self._client: Optional[OpenAI] = None
        self._platform = None

    def _pick_client(self, exclude: Optional[Set[str]] = None) -> Optional[OpenAI]:
        """遍历平台列表，返回第一个连通且未被排除的 client。"""
        exclude = exclude or set()
        for p in PLATFORMS:
            if p.name in exclude:
                continue
            try:
                client = OpenAI(api_key=p.api_key, base_url=p.base_url, timeout=DEFAULT_TIMEOUT)
                r = client.chat.completions.create(
                    model=p.model,
                    messages=[{"role": "user", "content": "回复两个字：在的"}],
                    max_tokens=20, temperature=0,
                )
                msg = r.choices[0].message
                probe = msg.content or getattr(msg, "reasoning_content", None) or ""
                if probe.strip():
                    self._client = client
                    self._platform = p
                    print(f"[LLM] 使用 {p.name} / {p.model}")
                    return client
            except Exception as e:
                print(f"[LLM] {p.name} 不可用: {str(e)[:120]}")
        return None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if self._pick_client() is None:
                raise RuntimeError("所有 LLM 平台均不可用")
        return self._client

    @property
    def platform_name(self) -> str:
        if self._platform is None:
            self.client  # 触发探活
        return self._platform.name if self._platform else "unknown"

    def _switch_platform(self, attempted: Set[str]) -> bool:
        """故障切换：从尚未尝试的平台中重新探活选一个。"""
        candidates = {p.name for p in PLATFORMS} - attempted
        if not candidates:
            return False
        print(f"[LLM] 当前平台故障，尝试切换备用平台（剩余: {sorted(candidates)}）")
        client = self._pick_client(exclude=attempted)
        if client is None:
            return False
        attempted.add(self._platform.name)
        return True

    def generate(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """统一调用入口。成功返回正文；不可恢复错误抛 LLMRequestError（带 kind）。"""
        if self._client is None and self._pick_client() is None:
            raise LLMRequestError(LLMErrorKind.NETWORK, "所有 LLM 平台启动探活均失败")

        attempted: Set[str] = {self._platform.name}
        cur_tokens = max_tokens
        last_err: Optional[LLMRequestError] = None

        for attempt in range(1, _HARD_ATTEMPT_CAP + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self._platform.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=temperature,
                    max_tokens=cur_tokens,
                )
                choice = resp.choices[0]
                content = choice.message.content
                finish_reason = getattr(choice, "finish_reason", None)

                if content and finish_reason != "length":
                    return content

                # 空正文（推理链占满）或输出被截断：归类后提升 token 预算
                if not content:
                    rc = getattr(choice.message, "reasoning_content", None)
                    last_err = LLMRequestError(
                        LLMErrorKind.EMPTY_RESPONSE,
                        f"AI 正文为空（推理链占满 token）。reasoning: {(rc or '')[:120]}",
                    )
                    cur_tokens = min(int(cur_tokens * 1.5), _TOKEN_HARD_CAP)
                else:
                    last_err = LLMRequestError(
                        LLMErrorKind.OUTPUT_TRUNCATED,
                        "AI 返回内容因输出 Token 上限被截断",
                    )
                    cur_tokens = min(max(cur_tokens * 2, max_tokens + 1024), _TOKEN_HARD_CAP)
            except Exception as e:
                last_err = normalize_llm_error(e)

            kind = last_err.kind
            action = GLOBAL_RETRY_POLICY.action_for(kind)

            # 服务级/配置级错误：先尝试备用平台，没有备用平台则交给执行器
            if action in ("pause_run", "fail_run", "raise"):
                if kind in (LLMErrorKind.QUOTA, LLMErrorKind.AUTH, LLMErrorKind.NETWORK,
                            LLMErrorKind.UNKNOWN, LLMErrorKind.TIMEOUT) and self._switch_platform(attempted):
                    continue
                raise last_err

            # 可重试错误：先退避；重试用尽后再试一次备用平台
            if GLOBAL_RETRY_POLICY.can_retry(kind, attempt):
                wait = GLOBAL_RETRY_POLICY.backoff_seconds(kind, attempt)
                print(f"  [LLM] {kind}，{wait:.0f}s 后重试（第{attempt}次），token={cur_tokens}")
                if wait:
                    time.sleep(wait)
                continue
            if self._switch_platform(attempted):
                continue
            raise last_err

        raise last_err or LLMRequestError(LLMErrorKind.UNKNOWN, "LLM 调用超过最大尝试次数")


# 全局单例
llm = LLMClient()
