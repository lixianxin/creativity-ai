# -*- coding: utf-8 -*-
"""Prompt 加载器：直接复用 agents/prompts/*.md，不复制内容。"""
from pathlib import Path

from core.config import PROMPT_DIR


def load_prompt(name: str) -> str:
    """按名称加载 prompt。
    name 可以是 'user_insight' 或 'user_insight_v1'，自动匹配 .md 文件。
    """
    # 优先精确匹配 name.md，再匹配 name_v1.md
    candidates = [PROMPT_DIR / f"{name}.md", PROMPT_DIR / f"{name}_v1.md"]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    # 模糊匹配：以 name 开头的第一个文件
    for f in PROMPT_DIR.glob(f"{name}*.md"):
        return f.read_text(encoding="utf-8")
    raise FileNotFoundError(f"未找到 prompt: {name}（搜索目录: {PROMPT_DIR}）")


def list_prompts() -> list:
    """列出所有可用 prompt 名称（去掉 _v1 后缀）。"""
    names = []
    for f in PROMPT_DIR.glob("*.md"):
        n = f.stem
        if n.endswith("_v1"):
            n = n[:-3]
        names.append(n)
    return sorted(names)
