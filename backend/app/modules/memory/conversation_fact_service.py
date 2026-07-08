import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.queue import get_default_queue
from app.shared.ids import new_id

CONVERSATION_FACT_SOURCE_TABLE = "conversation_memory_extract"
CONVERSATION_FACT_SOURCE_TYPE = "risk_chat"
CONVERSATION_FACT_RULE_VERSION = "conversation_fact_v1"
CONVERSATION_FACT_MEMORY_SCOPE = "customer"
CONVERSATION_FACT_MAX_WINDOW_MESSAGES = 12

_QUESTION_MARKERS = ("?", "？", "吗", "么", "呢", "为何", "为什么", "怎么", "是否", "是不是", "要不要", "会不会", "能不能")
_UNCERTAIN_MARKERS = ("可能", "也许", "大概", "猜测", "怀疑", "不确定", "待确认", "如果", "建议", "应该", "可以")
_CUSTOMER_SUBJECT_MARKERS = ("客户", "对方", "采购", "决策人", "老板", "负责人")
_WORLD_FACT_MARKERS = (
    "预算",
    "roi",
    "竞品",
    "偏好",
    "喜欢",
    "倾向",
    "优先",
    "微信",
    "电话",
    "邮件",
    "决策人",
    "采购时间",
    "采购周期",
    "拍板",
)
_OBSERVATION_MARKERS = ("表示", "反馈", "提到", "确认", "决定", "要求", "强调", "担心", "关注", "说明")


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _loads_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in messages:
        content = _normalize_text(item.get("content"))
        if not content:
            continue
        normalized.append(
            {
                "role": str(item.get("role") or "assistant"),
                "content": content,
                "created_at": str(item.get("created_at") or datetime.now().isoformat()),
            }
        )
    return normalized


def _split_sentences(content: str) -> list[str]:
    sentences = re.split(r"[。！？!?；;\n]+", content)
    return [_normalize_text(sentence) for sentence in sentences if _normalize_text(sentence)]


def _looks_like_question(sentence: str) -> bool:
    return any(marker in sentence for marker in _QUESTION_MARKERS)


def _contains_uncertainty(sentence: str) -> bool:
    return any(marker in sentence for marker in _UNCERTAIN_MARKERS)


def _contains_customer_subject(sentence: str) -> bool:
    return any(marker in sentence for marker in _CUSTOMER_SUBJECT_MARKERS)


def _classify_memory_type(sentence: str) -> str | None:
    lowered = sentence.lower()
    if any(marker in lowered for marker in _WORLD_FACT_MARKERS):
        return "world"
    if any(marker in sentence for marker in _OBSERVATION_MARKERS):
        return "observation"
    if _contains_customer_subject(sentence):
        return "observation"
    return None


def _build_fact_title(sentence: str, memory_type: str) -> str:
    lowered = sentence.lower()
    if "预算" in sentence:
        return "客户预算事实"
    if any(marker in lowered for marker in ("微信", "电话", "邮件")):
        return "客户沟通偏好"
    if "竞品" in sentence:
        return "客户竞品事实"
    if "roi" in lowered:
        return "客户ROI关注点"
    if any(marker in sentence for marker in ("决策人", "拍板")):
        return "客户决策事实"
    return "客户长期事实" if memory_type == "world" else "客户长期观察"


def _extract_entity_keys(sentence: str, customer_id: str) -> list[str]:
    entity_keys = [f"customer:{customer_id}"]
    for keyword in ("预算", "ROI", "竞品", "微信", "电话", "邮件", "决策人", "采购时间", "采购周期"):
        if keyword.lower() in sentence.lower() or keyword in sentence:
            entity_keys.append(keyword.lower())
    return entity_keys


def extract_long_term_facts_from_conversation(
    *,
    customer_id: str,
    session_key: str,
    source_type: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for message in _normalize_messages(messages):
        role = str(message.get("role") or "assistant")
        for sentence in _split_sentences(str(message.get("content") or "")):
            if len(sentence) < 6 or len(sentence) > 120:
                continue
            if not _contains_customer_subject(sentence):
                continue
            if _looks_like_question(sentence) or _contains_uncertainty(sentence):
                continue
            memory_type = _classify_memory_type(sentence)
            if memory_type not in {"world", "observation"}:
                continue

            dedupe_key = f"{memory_type}:{_normalize_text(sentence).lower()}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            facts.append(
                {
                    "memory_type": memory_type,
                    "title": _build_fact_title(sentence, memory_type),
                    "content": sentence,
                    "occurred_at": message.get("created_at"),
                    "evidence_refs": [f"{session_key}:{role}:{message.get('created_at')}"],
                    "entity_keys": _extract_entity_keys(sentence, customer_id),
                    "metadata_json": {
                        "source_type": source_type,
                        "rule_version": CONVERSATION_FACT_RULE_VERSION,
                        "dedupe_key": dedupe_key,
                        "extracted_from_role": role,
                    },
                }
            )
            if len(facts) >= 5:
                return facts
    return facts


def _load_current_memory_id(db, *, tenant_id: str, customer_id: str) -> str:
    memory_id = db.execute(
        text(
            """
            SELECT memory_id
            FROM customer_memory
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
              AND memory_scope = 'customer'
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).scalar_one_or_none()
    return str(memory_id or f"conversation_memory:{customer_id}")


def _merge_unique_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = _normalize_text(value)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def _load_existing_conversation_facts(db, *, tenant_id: str, customer_id: str) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT atomic_memory_id, memory_id, order_index, title, content, occurred_at,
                   evidence_refs_json, entity_keys_json, metadata_json
            FROM customer_memory_atomic
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
              AND memory_scope = 'customer'
              AND source_table = :source_table
            ORDER BY order_index ASC, created_at ASC
            """
        ),
        {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "source_table": CONVERSATION_FACT_SOURCE_TABLE,
        },
    ).mappings().all()
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        metadata_json = _loads_json(item.get("metadata_json"))
        dedupe_key = str(metadata_json.get("dedupe_key") or "").strip()
        if dedupe_key:
            indexed[dedupe_key] = item
    return indexed


def _persist_conversation_facts(
    db,
    *,
    tenant_id: str,
    customer_id: str,
    extract_job_id: str,
    facts: list[dict[str, Any]],
) -> dict[str, int]:
    if not facts:
        return {"inserted_count": 0, "updated_count": 0}

    memory_id = _load_current_memory_id(db, tenant_id=tenant_id, customer_id=customer_id)
    existing = _load_existing_conversation_facts(db, tenant_id=tenant_id, customer_id=customer_id)
    next_order = (
        db.execute(
            text(
                """
                SELECT COALESCE(MAX(order_index), 0)
                FROM customer_memory_atomic
                WHERE tenant_id = :tenant_id
                  AND customer_id = :customer_id
                  AND memory_scope = 'customer'
                """
            ),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        ).scalar_one()
        or 0
    )

    inserted_count = 0
    updated_count = 0
    for fact in facts:
        metadata_json = dict(fact.get("metadata_json") or {})
        dedupe_key = str(metadata_json.get("dedupe_key") or "").strip()
        existing_item = existing.get(dedupe_key)
        if existing_item:
            merged_evidence = _merge_unique_values(
                [
                    *_loads_json_list(existing_item.get("evidence_refs_json")),
                    *(fact.get("evidence_refs") or []),
                ]
            )
            merged_entities = _merge_unique_values(
                [
                    *_loads_json_list(existing_item.get("entity_keys_json")),
                    *(fact.get("entity_keys") or []),
                ]
            )
            merged_metadata = {
                **_loads_json(existing_item.get("metadata_json")),
                **metadata_json,
                "last_extract_job_id": extract_job_id,
                "last_seen_at": datetime.now().isoformat(),
            }
            db.execute(
                text(
                    """
                    UPDATE customer_memory_atomic
                    SET memory_id = :memory_id,
                        title = :title,
                        content = :content,
                        occurred_at = :occurred_at,
                        source_id = :source_id,
                        evidence_refs_json = :evidence_refs_json,
                        entity_keys_json = :entity_keys_json,
                        metadata_json = :metadata_json
                    WHERE atomic_memory_id = :atomic_memory_id
                    """
                ),
                {
                    "memory_id": memory_id,
                    "title": fact.get("title"),
                    "content": fact.get("content"),
                    "occurred_at": fact.get("occurred_at"),
                    "source_id": extract_job_id,
                    "evidence_refs_json": _dumps_json(merged_evidence),
                    "entity_keys_json": _dumps_json(merged_entities),
                    "metadata_json": _dumps_json(merged_metadata),
                    "atomic_memory_id": existing_item["atomic_memory_id"],
                },
            )
            updated_count += 1
            continue

        next_order += 1
        db.execute(
            text(
                """
                INSERT INTO customer_memory_atomic (
                  tenant_id, atomic_memory_id, memory_id, customer_id, memory_scope, memory_type,
                  order_index, title, content, confidence, occurred_at, source_table, source_id,
                  source_run_id, evidence_refs_json, entity_keys_json, metadata_json
                )
                VALUES (
                  :tenant_id, :atomic_memory_id, :memory_id, :customer_id, :memory_scope, :memory_type,
                  :order_index, :title, :content, NULL, :occurred_at, :source_table, :source_id,
                  NULL, :evidence_refs_json, :entity_keys_json, :metadata_json
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "atomic_memory_id": new_id("mematom"),
                "memory_id": memory_id,
                "customer_id": customer_id,
                "memory_scope": CONVERSATION_FACT_MEMORY_SCOPE,
                "memory_type": fact["memory_type"],
                "order_index": next_order,
                "title": fact.get("title"),
                "content": fact["content"],
                "occurred_at": fact.get("occurred_at"),
                "source_table": CONVERSATION_FACT_SOURCE_TABLE,
                "source_id": extract_job_id,
                "evidence_refs_json": _dumps_json(fact.get("evidence_refs") or []),
                "entity_keys_json": _dumps_json(fact.get("entity_keys") or []),
                "metadata_json": _dumps_json(
                    {
                        **metadata_json,
                        "created_by_extract_job_id": extract_job_id,
                        "created_at": datetime.now().isoformat(),
                    }
                ),
            },
        )
        inserted_count += 1
    return {"inserted_count": inserted_count, "updated_count": updated_count}


def enqueue_conversation_fact_extraction(
    *,
    tenant_id: str,
    user_id: str,
    customer_id: str,
    session_key: str,
    source_type: str,
    trigger_messages: list[dict[str, Any]],
    recent_messages: list[dict[str, Any]],
    history_summary: str,
) -> dict[str, Any] | None:
    normalized_batch = _normalize_messages(trigger_messages)
    if not normalized_batch:
        return None

    normalized_window = _normalize_messages(recent_messages)[-CONVERSATION_FACT_MAX_WINDOW_MESSAGES:]
    extract_job_id = new_id("memxjob")
    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO conversation_memory_extract_job (
                  tenant_id, extract_job_id, customer_id, user_id, source_type, session_key, status,
                  trigger_message_count, trigger_batch_json, recent_window_json, history_summary
                )
                VALUES (
                  :tenant_id, :extract_job_id, :customer_id, :user_id, :source_type, :session_key, 'queued',
                  :trigger_message_count, :trigger_batch_json, :recent_window_json, :history_summary
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "extract_job_id": extract_job_id,
                "customer_id": customer_id,
                "user_id": user_id,
                "source_type": source_type,
                "session_key": session_key,
                "trigger_message_count": len(normalized_batch),
                "trigger_batch_json": _dumps_json(normalized_batch),
                "recent_window_json": _dumps_json(normalized_window),
                "history_summary": history_summary or None,
            },
        )
        db.commit()

        try:
            job = get_default_queue().enqueue(
                "app.workers.memory_jobs.extract_customer_long_term_facts",
                tenant_id,
                user_id,
                extract_job_id,
                job_timeout=600,
            )
            db.execute(
                text(
                    """
                    UPDATE conversation_memory_extract_job
                    SET queued_job_id = :queued_job_id
                    WHERE tenant_id = :tenant_id
                      AND extract_job_id = :extract_job_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "extract_job_id": extract_job_id,
                    "queued_job_id": getattr(job, "id", None),
                },
            )
            db.commit()
            return {
                "extract_job_id": extract_job_id,
                "queued_job_id": getattr(job, "id", None),
                "status": "queued",
            }
        except Exception as exc:
            db.execute(
                text(
                    """
                    UPDATE conversation_memory_extract_job
                    SET status = 'failed',
                        error_message = :error_message,
                        finished_at = NOW()
                    WHERE tenant_id = :tenant_id
                      AND extract_job_id = :extract_job_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "extract_job_id": extract_job_id,
                    "error_message": str(exc)[:1000],
                },
            )
            db.commit()
            return {
                "extract_job_id": extract_job_id,
                "queued_job_id": None,
                "status": "failed",
                "error_message": str(exc),
            }


def run_conversation_long_term_fact_extraction_job(
    tenant_id: str,
    user_id: str,
    extract_job_id: str,
) -> dict[str, Any]:
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT extract_job_id, tenant_id, customer_id, user_id, source_type, session_key, status,
                       trigger_batch_json, recent_window_json, history_summary
                FROM conversation_memory_extract_job
                WHERE tenant_id = :tenant_id
                  AND extract_job_id = :extract_job_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "extract_job_id": extract_job_id},
        ).mappings().first()
        if not row:
            raise ValueError("长期事实抽取任务不存在")
        job = dict(row)
        if str(job.get("user_id") or "") != str(user_id):
            raise ValueError("长期事实抽取任务无权访问")

        db.execute(
            text(
                """
                UPDATE conversation_memory_extract_job
                SET status = 'running',
                    started_at = NOW(),
                    error_message = NULL
                WHERE tenant_id = :tenant_id
                  AND extract_job_id = :extract_job_id
                """
            ),
            {"tenant_id": tenant_id, "extract_job_id": extract_job_id},
        )
        db.commit()

        try:
            trigger_batch = _loads_json_list(job.get("trigger_batch_json"))
            recent_window = _loads_json_list(job.get("recent_window_json"))
            facts = extract_long_term_facts_from_conversation(
                customer_id=str(job["customer_id"]),
                session_key=str(job.get("session_key") or ""),
                source_type=str(job.get("source_type") or CONVERSATION_FACT_SOURCE_TYPE),
                messages=[*recent_window, *trigger_batch],
            )
            persist_result = _persist_conversation_facts(
                db,
                tenant_id=tenant_id,
                customer_id=str(job["customer_id"]),
                extract_job_id=extract_job_id,
                facts=facts,
            )
            db.execute(
                text(
                    """
                    UPDATE conversation_memory_extract_job
                    SET status = 'success',
                        extracted_facts_json = :extracted_facts_json,
                        error_message = NULL,
                        finished_at = NOW()
                    WHERE tenant_id = :tenant_id
                      AND extract_job_id = :extract_job_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "extract_job_id": extract_job_id,
                    "extracted_facts_json": _dumps_json(facts),
                },
            )
            db.commit()
            return {
                "extract_job_id": extract_job_id,
                "customer_id": job["customer_id"],
                "fact_count": len(facts),
                **persist_result,
            }
        except Exception as exc:
            db.rollback()
            db.execute(
                text(
                    """
                    UPDATE conversation_memory_extract_job
                    SET status = 'failed',
                        error_message = :error_message,
                        finished_at = NOW()
                    WHERE tenant_id = :tenant_id
                      AND extract_job_id = :extract_job_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "extract_job_id": extract_job_id,
                    "error_message": str(exc)[:1000],
                },
            )
            db.commit()
            raise
