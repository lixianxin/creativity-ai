# -*- coding: utf-8 -*-
"""Agent 基类（Phase 7-5 加固）：LLM 调用缓存、校验返工、结果统一构造。

子类契约不变（只需指定 prompt_name 并实现 run），返工能力由基类统一提供，
12 个 Agent 子类零改动即可接入 ResultValidator 闸门。
"""
import time
from abc import ABC, abstractmethod
from typing import Optional

from core.llm_client import llm
from core.prompt_loader import load_prompt
from schemas.agent_result import AgentResult, STATUS_SUCCESS


class BaseAgent(ABC):
    """所有 Agent 的基类。子类只需指定 prompt_name 并实现 run 方法。"""

    prompt_name: str = ""  # 子类覆盖，对应 agents/prompts/<name>_v1.md

    def __init__(self):
        if not self.prompt_name:
            raise ValueError(f"{self.__class__.__name__} 未指定 prompt_name")
        self.system_prompt = load_prompt(self.prompt_name)
        # 返工所需的最近一次调用上下文（执行器在校验不通过时使用）
        self._last_user_content: Optional[str] = None
        self._last_max_tokens: int = 16000
        self._last_result: Optional[AgentResult] = None

    def _call_llm(self, user_content: str, max_tokens: int = 16000) -> str:
        """调用 LLM，返回正文；同时缓存本次调用上下文供校验返工使用。"""
        self._last_user_content = user_content
        self._last_max_tokens = max_tokens
        t0 = time.time()
        content = llm.generate(self.system_prompt, user_content, max_tokens=max_tokens)
        elapsed = round(time.time() - t0, 1)
        print(f"  [{self.prompt_name}] LLM 调用完成，{elapsed}s，{len(content)}字")
        return content

    def repair(self, issues_text: str) -> str:
        """校验不通过后的一次返工：带系统反馈重写，返回新的完整报告正文。"""
        if not self._last_user_content:
            raise RuntimeError(f"{self.prompt_name} 无可返工的上一次调用上下文")
        repair_user = (
            f"{self._last_user_content}\n\n"
            f"==== 你上一版输出 ====\n{self._last_result.raw_output if self._last_result else ''}\n\n"
            f"==== 系统校验反馈（必须逐条修正） ====\n{issues_text}"
        )
        t0 = time.time()
        content = llm.generate(self.system_prompt, repair_user, max_tokens=self._last_max_tokens)
        print(f"  [{self.prompt_name}] 校验返工完成，{round(time.time() - t0, 1)}s，{len(content)}字")
        return content

    @abstractmethod
    def run(self, project_input: str, context: dict = None) -> AgentResult:
        """子类实现：输入项目描述 + 上下文，返回 AgentResult。"""
        pass

    def rebuild_after_repair(self, new_raw: str) -> AgentResult:
        """返工后重建结果。

        完整报告以 new_raw 为准；关键字段（conclusion/blocking/redline 等）
        随后由 ResultValidator 的程序信号覆盖，这里只做保守的通用解析。
        """
        lines = [l.strip() for l in new_raw.split("\n") if l.strip()]
        summary = lines[0][:100] if lines else new_raw[:100]
        old = self._last_result
        result = self._build_result(
            summary=summary,
            raw_output=new_raw,
            evidence=list(old.evidence) if old else [],
            risks=list(old.risks) if old else [],
            confidence=old.confidence if old else 0.0,
            conclusion=old.conclusion if old else "",
            metadata={**(old.metadata if old else {}), "chars": len(new_raw), "repaired": True},
        )
        self._last_result = result
        return result

    def _build_result(
        self,
        summary: str,
        raw_output: str,
        evidence=None,
        risks=None,
        confidence: float = 0.0,
        conclusion: str = "",
        metadata=None,
    ) -> AgentResult:
        """统一构造 AgentResult。"""
        result = AgentResult(
            agent_name=self.prompt_name,
            status=STATUS_SUCCESS,
            summary=summary,
            conclusion=conclusion,
            evidence=evidence or [],
            risks=risks or [],
            confidence=confidence,
            raw_output=raw_output,
            metadata=metadata or {},
        )
        self._last_result = result
        return result
