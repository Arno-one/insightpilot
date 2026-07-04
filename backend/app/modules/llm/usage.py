import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.shared.ids import new_id

logger = logging.getLogger(__name__)


def _usage_value(usage: Any, field_name: str) -> int:
    """中文注释：兼容 OpenAI SDK 对象和测试里的 dict，避免不同响应形态打断日志记录。"""
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(field_name) or 0)
    return int(getattr(usage, field_name, 0) or 0)


def extract_token_usage(response: Any) -> dict[str, int]:
    """中文注释：从 LLM 响应中抽取 token 用量；没有 usage 时返回 0，保持调用链稳定。"""
    usage = getattr(response, "usage", None)
    prompt_tokens = _usage_value(usage, "prompt_tokens")
    completion_tokens = _usage_value(usage, "completion_tokens")
    total_tokens = _usage_value(usage, "total_tokens") or prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def estimate_llm_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    input_unit_cost: Decimal = Decimal("0"),
    output_unit_cost: Decimal = Decimal("0"),
) -> Decimal:
    """中文注释：V1 先预留成本算法入口，默认单价为 0，后续接入模型价格表时无需改调用方。"""
    prompt_cost = Decimal(prompt_tokens) * input_unit_cost / Decimal(1000)
    completion_cost = Decimal(completion_tokens) * output_unit_cost / Decimal(1000)
    return (prompt_cost + completion_cost).quantize(Decimal("0.000001"))


def record_llm_call(
    *,
    tenant_id: str,
    source: str,
    model: str,
    provider: str = "deepseek",
    user_id: str | None = None,
    status: str = "success",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    estimated_cost: Decimal | float | str = Decimal("0"),
    currency: str = "USD",
    error_message: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> str | None:
    """中文注释：写入 LLM 调用观测日志；失败只记应用日志，不反向影响主业务链路。"""
    call_id = new_id("llmcall")
    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO llm_call_log (
                      tenant_id, call_id, user_id, source, provider, model, status,
                      prompt_tokens, completion_tokens, total_tokens, latency_ms,
                      estimated_cost, currency, error_message, metadata_json
                    )
                    VALUES (
                      :tenant_id, :call_id, :user_id, :source, :provider, :model, :status,
                      :prompt_tokens, :completion_tokens, :total_tokens, :latency_ms,
                      :estimated_cost, :currency, :error_message, :metadata_json
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "call_id": call_id,
                    "user_id": user_id,
                    "source": source,
                    "provider": provider,
                    "model": model,
                    "status": status,
                    "prompt_tokens": int(prompt_tokens or 0),
                    "completion_tokens": int(completion_tokens or 0),
                    "total_tokens": int(total_tokens or 0),
                    "latency_ms": int(latency_ms or 0),
                    "estimated_cost": str(estimated_cost or Decimal("0")),
                    "currency": currency,
                    "error_message": error_message,
                    "metadata_json": json.dumps(metadata_json or {}, ensure_ascii=False, default=str),
                },
            )
            db.commit()
        return call_id
    except SQLAlchemyError as exc:
        logger.warning("LLM 调用日志写入失败，主流程继续: %s", exc)
        return None
