# -*- coding: utf-8 -*-
"""全局配置：模型平台列表、API Key、默认参数。"""
import os
from dataclasses import dataclass
from typing import List


@dataclass
class Platform:
    name: str
    base_url: str
    api_key: str
    model: str


# 平台优先级：DeepSeek 主，百炼/智谱备用
# Phase 7-10 部署安全：密钥改为「环境变量优先，内置值仅本地开发回退」。
# 公网部署（Streamlit Cloud / 服务器）必须通过环境变量或 .streamlit/secrets.toml
# 注入密钥，切勿依赖源码中的回退值；赛事结束后建议轮换全部密钥。
PLATFORMS: List[Platform] = [
    Platform(
        name="deepseek",
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    ),
    Platform(
        name="bailian",
        base_url=os.environ.get("BAILIAN_BASE_URL",
                                "https://llm-969nmsfu6bcf8ozc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"),
        api_key=os.environ.get("BAILIAN_API_KEY", ""),
        model=os.environ.get("BAILIAN_MODEL", "qwen-plus"),
    ),
    Platform(
        name="zhipu",
        base_url=os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        api_key=os.environ.get("ZHIPU_API_KEY",
                               ""),
        model=os.environ.get("ZHIPU_MODEL", "glm-5.1"),
    ),
]

# 默认生成参数
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 16000
DEFAULT_TIMEOUT = 120

# 项目根目录（动态解析，避免相对路径问题）
import pathlib
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
PROMPT_DIR = PROJECT_ROOT / "agents" / "prompts"
