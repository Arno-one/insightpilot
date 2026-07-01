"""LLM 兼容入口。

新项目的真实 LLM 能力位于 `backend/app/modules/llm/client.py`。
保留根目录入口是为了兼容临时脚本，同时避免旧项目的 util/log 依赖污染新项目。
"""
from pathlib import Path
from typing import Type
import sys

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.modules.llm.client import structured_complete as _structured_complete  # noqa: E402


def get_model(provider: str = "deepseek"):
    """返回底层 OpenAI 兼容客户端；当前项目默认使用 DeepSeek。"""
    if provider != "deepseek":
        raise ValueError(f"当前 InsightPilot V1 只启用 deepseek provider: {provider}")
    from openai import OpenAI

    return OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)


def structured_complete(
    system_prompt: str,
    user_message: str,
    schema: Type[BaseModel],
    provider: str = "deepseek",
) -> dict:
    """调用 LLM 并返回兼容旧用法的结构化结果。"""
    if provider != "deepseek":
        return {"parsed": None, "error": f"不支持的 provider: {provider}"}
    parsed = _structured_complete(system_prompt, user_message, schema)
    if parsed is None:
        return {"parsed": None, "error": "模型调用失败或返回格式异常"}
    return {"parsed": parsed, "error": None}
