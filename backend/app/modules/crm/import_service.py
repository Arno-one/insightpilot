import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session


IMPORT_ENTITY_CUSTOMER = "customer"
IMPORT_ENTITY_DEAL = "deal"
IMPORT_ENTITY_FOLLOW_UP = "follow_up"

IMPORT_REQUIRED_FIELDS = {
    IMPORT_ENTITY_CUSTOMER: [
        "customer_id",
        "customer_name",
        "owner_user_id",
        "lifecycle_stage",
        "intent_level",
        "customer_level",
        "industry",
        "region",
        "next_follow_up_at",
        "remark",
    ],
    IMPORT_ENTITY_DEAL: [
        "deal_id",
        "customer_id",
        "owner_user_id",
        "deal_name",
        "stage",
        "amount",
        "quote_amount",
        "quoted_at",
        "expected_close_at",
        "close_result",
    ],
    IMPORT_ENTITY_FOLLOW_UP: [
        "follow_up_id",
        "customer_id",
        "deal_id",
        "owner_user_id",
        "follow_up_type",
        "content",
        "sentiment",
        "next_action",
        "next_follow_up_at",
        "occurred_at",
    ],
}

IMPORT_FILE_NAMES = {
    IMPORT_ENTITY_CUSTOMER: "crm_customer_template.csv",
    IMPORT_ENTITY_DEAL: "crm_deal_template.csv",
    IMPORT_ENTITY_FOLLOW_UP: "crm_follow_up_template.csv",
}

CUSTOMER_LIFECYCLE_STAGES = {"new_lead", "communicated", "solution", "quotation", "won", "lost"}
INTENT_LEVELS = {"low", "medium", "high"}
CUSTOMER_LEVELS = {"A", "B", "C"}
DEAL_STAGES = {"communicated", "solution", "quotation", "won", "lost"}
CLOSE_RESULTS = {"open", "won", "lost"}
FOLLOW_UP_TYPES = {"phone", "wechat", "meeting", "email"}
SENTIMENTS = {"positive", "neutral", "negative"}


@dataclass
class ImportFailure:
    row_no: int
    business_key: str
    reason: str
    row_data: dict[str, str]


def build_template_csv(entity: str) -> tuple[str, str]:
    """返回导入模板的文件名和 CSV 文本内容。"""
    fields = IMPORT_REQUIRED_FIELDS.get(entity)
    if not fields:
        raise HTTPException(status_code=404, detail="不支持的导入类型")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)
    return IMPORT_FILE_NAMES[entity], buffer.getvalue()


async def import_csv_file(entity: str, upload_file: UploadFile, current_user: dict, db: Session) -> dict:
    """按实体类型执行 CSV 导入，遵循只新增不覆盖的约束。"""
    if entity not in IMPORT_REQUIRED_FIELDS:
        raise HTTPException(status_code=404, detail="不支持的导入类型")
    if not upload_file.filename or not upload_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件")

    raw_bytes = await upload_file.read()
    rows = _read_csv_rows(raw_bytes, entity)

    users = _load_active_users(db, current_user["tenant_id"])
    existing_keys = _load_existing_business_keys(db, current_user["tenant_id"])
    visible_customers = _load_visible_customers(db, current_user)
    visible_deals = _load_visible_deals(db, current_user)

    inserted_rows: list[str] = []
    failures: list[ImportFailure] = []
    seen_keys: set[str] = set()
    follow_up_customer_updates: dict[str, dict] = {}

    for row_no, row_data in rows:
        business_key = _business_key_for_entity(entity, row_data)
        if not business_key:
            failures.append(ImportFailure(row_no, "", "业务主键不能为空", row_data))
            continue
        if business_key in seen_keys:
            failures.append(ImportFailure(row_no, business_key, "同一个文件里出现了重复业务主键", row_data))
            continue
        seen_keys.add(business_key)

        if business_key in existing_keys[entity]:
            failures.append(ImportFailure(row_no, business_key, "该业务主键已存在，当前策略为只新增不覆盖", row_data))
            continue

        try:
            if entity == IMPORT_ENTITY_CUSTOMER:
                insert_payload = _validate_customer_row(row_data, current_user, users)
                db.execute(
                    text(
                        """
                        INSERT INTO crm_customer (
                          tenant_id, customer_id, customer_name, owner_user_id, lifecycle_stage,
                          intent_level, customer_level, industry, region, next_follow_up_at, remark
                        )
                        VALUES (
                          :tenant_id, :customer_id, :customer_name, :owner_user_id, :lifecycle_stage,
                          :intent_level, :customer_level, :industry, :region, :next_follow_up_at, :remark
                        )
                        """
                    ),
                    {"tenant_id": current_user["tenant_id"], **insert_payload},
                )
                visible_customers[insert_payload["customer_id"]] = {
                    "customer_id": insert_payload["customer_id"],
                    "owner_user_id": insert_payload["owner_user_id"],
                }
            elif entity == IMPORT_ENTITY_DEAL:
                insert_payload = _validate_deal_row(row_data, current_user, users, visible_customers)
                db.execute(
                    text(
                        """
                        INSERT INTO crm_deal (
                          tenant_id, deal_id, customer_id, owner_user_id, deal_name, stage,
                          amount, quote_amount, quoted_at, expected_close_at, close_result
                        )
                        VALUES (
                          :tenant_id, :deal_id, :customer_id, :owner_user_id, :deal_name, :stage,
                          :amount, :quote_amount, :quoted_at, :expected_close_at, :close_result
                        )
                        """
                    ),
                    {"tenant_id": current_user["tenant_id"], **insert_payload},
                )
                visible_deals[insert_payload["deal_id"]] = {
                    "deal_id": insert_payload["deal_id"],
                    "customer_id": insert_payload["customer_id"],
                }
            else:
                insert_payload = _validate_follow_up_row(row_data, current_user, users, visible_customers, visible_deals)
                db.execute(
                    text(
                        """
                        INSERT INTO crm_follow_up_record (
                          tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type,
                          content, sentiment, next_action, next_follow_up_at, occurred_at
                        )
                        VALUES (
                          :tenant_id, :follow_up_id, :customer_id, :deal_id, :owner_user_id, :follow_up_type,
                          :content, :sentiment, :next_action, :next_follow_up_at, :occurred_at
                        )
                        """
                    ),
                    {"tenant_id": current_user["tenant_id"], **insert_payload},
                )
                _merge_follow_up_customer_update(follow_up_customer_updates, insert_payload)
        except ValueError as exc:
            failures.append(ImportFailure(row_no, business_key, str(exc), row_data))
            continue

        inserted_rows.append(business_key)

    _apply_follow_up_customer_updates(db, current_user["tenant_id"], follow_up_customer_updates)
    db.commit()

    return {
        "entity": entity,
        "file_name": upload_file.filename,
        "total_count": len(rows),
        "success_count": len(inserted_rows),
        "failed_count": len(failures),
        "inserted_keys": inserted_rows,
        "failures": [
            {
                "row_no": failure.row_no,
                "business_key": failure.business_key,
                "reason": failure.reason,
                "row_data": failure.row_data,
            }
            for failure in failures
        ],
        "failed_rows_csv": _build_failed_rows_csv(entity, failures),
    }


def _read_csv_rows(raw_bytes: bytes, entity: str) -> list[tuple[int, dict[str, str]]]:
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        text_content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV 需要使用 UTF-8 编码保存") from exc

    reader = csv.DictReader(io.StringIO(text_content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 缺少表头")

    normalized_headers = [header.strip() if header else "" for header in reader.fieldnames]
    reader.fieldnames = normalized_headers

    required_fields = IMPORT_REQUIRED_FIELDS[entity]
    missing_fields = [field for field in required_fields if field not in normalized_headers]
    if missing_fields:
        raise HTTPException(status_code=400, detail=f"CSV 缺少必需字段: {', '.join(missing_fields)}")

    rows: list[tuple[int, dict[str, str]]] = []
    for row_no, row in enumerate(reader, start=2):
        normalized_row = {field: _clean_csv_value(row.get(field)) for field in normalized_headers}
        if not any(normalized_row.values()):
            continue
        rows.append((row_no, normalized_row))
    return rows


def _clean_csv_value(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def _load_active_users(db: Session, tenant_id: str) -> dict[str, dict]:
    rows = db.execute(
        text(
            """
            SELECT user_id, real_name
            FROM sys_user
            WHERE tenant_id = :tenant_id AND status = 1 AND is_deleted = 0
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    return {row["user_id"]: dict(row) for row in rows}


def _load_existing_business_keys(db: Session, tenant_id: str) -> dict[str, set[str]]:
    customer_ids = db.execute(
        text("SELECT customer_id FROM crm_customer WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    ).scalars().all()
    deal_ids = db.execute(
        text("SELECT deal_id FROM crm_deal WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    ).scalars().all()
    follow_up_ids = db.execute(
        text("SELECT follow_up_id FROM crm_follow_up_record WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    ).scalars().all()
    return {
        IMPORT_ENTITY_CUSTOMER: set(customer_ids),
        IMPORT_ENTITY_DEAL: set(deal_ids),
        IMPORT_ENTITY_FOLLOW_UP: set(follow_up_ids),
    }


def _load_visible_customers(db: Session, current_user: dict) -> dict[str, dict]:
    scope_sql = _visible_customer_scope_sql(current_user, "c")
    rows = db.execute(
        text(
            f"""
            SELECT c.customer_id, c.owner_user_id
            FROM crm_customer c
            WHERE {scope_sql}
            """
        ),
        {"tenant_id": current_user["tenant_id"], "user_id": current_user["user_id"]},
    ).mappings().all()
    return {row["customer_id"]: dict(row) for row in rows}


def _load_visible_deals(db: Session, current_user: dict) -> dict[str, dict]:
    scope_sql = _visible_customer_scope_sql(current_user, "c")
    rows = db.execute(
        text(
            f"""
            SELECT d.deal_id, d.customer_id
            FROM crm_deal d
            JOIN crm_customer c
              ON c.tenant_id = d.tenant_id
             AND c.customer_id = d.customer_id
            WHERE {scope_sql}
            """
        ),
        {"tenant_id": current_user["tenant_id"], "user_id": current_user["user_id"]},
    ).mappings().all()
    return {row["deal_id"]: dict(row) for row in rows}


def _visible_customer_scope_sql(current_user: dict, alias: str) -> str:
    prefix = f"{alias}." if alias else ""
    if "crm:customer:read:all" in current_user["permission_codes"]:
        return f"{prefix}tenant_id = :tenant_id"
    if "crm:customer:read:team" in current_user["permission_codes"]:
        return f"{prefix}tenant_id = :tenant_id"
    return f"{prefix}tenant_id = :tenant_id AND {prefix}owner_user_id = :user_id"


def _validate_customer_row(row: dict[str, str], current_user: dict, users: dict[str, dict]) -> dict:
    customer_id = _require_text(row, "customer_id")
    customer_name = _require_text(row, "customer_name")
    owner_user_id = _require_text(row, "owner_user_id")
    lifecycle_stage = _require_choice(row, "lifecycle_stage", CUSTOMER_LIFECYCLE_STAGES)
    intent_level = _require_choice(row, "intent_level", INTENT_LEVELS)
    customer_level = _require_choice(row, "customer_level", CUSTOMER_LEVELS)

    _ensure_owner_allowed(current_user, owner_user_id, users)

    return {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "owner_user_id": owner_user_id,
        "lifecycle_stage": lifecycle_stage,
        "intent_level": intent_level,
        "customer_level": customer_level,
        "industry": _optional_text(row, "industry"),
        "region": _optional_text(row, "region"),
        "next_follow_up_at": _optional_datetime(row, "next_follow_up_at"),
        "remark": _optional_text(row, "remark"),
    }


def _validate_deal_row(
    row: dict[str, str],
    current_user: dict,
    users: dict[str, dict],
    visible_customers: dict[str, dict],
) -> dict:
    deal_id = _require_text(row, "deal_id")
    customer_id = _require_text(row, "customer_id")
    owner_user_id = _require_text(row, "owner_user_id")
    deal_name = _require_text(row, "deal_name")
    stage = _require_choice(row, "stage", DEAL_STAGES)
    amount = _require_decimal(row, "amount")
    close_result = _require_choice(row, "close_result", CLOSE_RESULTS)

    _ensure_owner_allowed(current_user, owner_user_id, users)
    _ensure_customer_visible(customer_id, visible_customers)

    return {
        "deal_id": deal_id,
        "customer_id": customer_id,
        "owner_user_id": owner_user_id,
        "deal_name": deal_name,
        "stage": stage,
        "amount": amount,
        "quote_amount": _optional_decimal(row, "quote_amount"),
        "quoted_at": _optional_datetime(row, "quoted_at"),
        "expected_close_at": _optional_date(row, "expected_close_at"),
        "close_result": close_result,
    }


def _validate_follow_up_row(
    row: dict[str, str],
    current_user: dict,
    users: dict[str, dict],
    visible_customers: dict[str, dict],
    visible_deals: dict[str, dict],
) -> dict:
    follow_up_id = _require_text(row, "follow_up_id")
    customer_id = _require_text(row, "customer_id")
    owner_user_id = _require_text(row, "owner_user_id")
    follow_up_type = _require_choice(row, "follow_up_type", FOLLOW_UP_TYPES)
    content = _require_text(row, "content")
    sentiment = _require_choice(row, "sentiment", SENTIMENTS)
    occurred_at = _require_datetime(row, "occurred_at")
    deal_id = _optional_text(row, "deal_id")

    _ensure_owner_allowed(current_user, owner_user_id, users)
    _ensure_customer_visible(customer_id, visible_customers)
    if deal_id:
        visible_deal = visible_deals.get(deal_id)
        if not visible_deal:
            raise ValueError("关联商机不存在或当前账号无权引用")
        if visible_deal["customer_id"] != customer_id:
            raise ValueError("关联商机不属于当前 customer_id")

    return {
        "follow_up_id": follow_up_id,
        "customer_id": customer_id,
        "deal_id": deal_id or None,
        "owner_user_id": owner_user_id,
        "follow_up_type": follow_up_type,
        "content": content,
        "sentiment": sentiment,
        "next_action": _optional_text(row, "next_action"),
        "next_follow_up_at": _optional_datetime(row, "next_follow_up_at"),
        "occurred_at": occurred_at,
    }


def _business_key_for_entity(entity: str, row: dict[str, str]) -> str:
    key_mapping = {
        IMPORT_ENTITY_CUSTOMER: "customer_id",
        IMPORT_ENTITY_DEAL: "deal_id",
        IMPORT_ENTITY_FOLLOW_UP: "follow_up_id",
    }
    return _clean_csv_value(row.get(key_mapping[entity]))


def _ensure_owner_allowed(current_user: dict, owner_user_id: str, users: dict[str, dict]):
    if owner_user_id not in users:
        raise ValueError("owner_user_id 不存在或已停用")
    if "crm:customer:read:all" in current_user["permission_codes"]:
        return
    if "crm:customer:read:team" in current_user["permission_codes"]:
        return
    if owner_user_id != current_user["user_id"]:
        raise ValueError("当前账号只有本人客户权限，owner_user_id 必须等于当前登录用户")


def _ensure_customer_visible(customer_id: str, visible_customers: dict[str, dict]):
    if customer_id not in visible_customers:
        raise ValueError("customer_id 不存在或当前账号无权引用")


def _require_text(row: dict[str, str], field: str) -> str:
    value = _clean_csv_value(row.get(field))
    if not value:
        raise ValueError(f"{field} 不能为空")
    return value


def _optional_text(row: dict[str, str], field: str) -> str | None:
    value = _clean_csv_value(row.get(field))
    return value or None


def _require_choice(row: dict[str, str], field: str, allowed_values: set[str]) -> str:
    value = _require_text(row, field)
    if value not in allowed_values:
        raise ValueError(f"{field} 只支持: {', '.join(sorted(allowed_values))}")
    return value


def _require_decimal(row: dict[str, str], field: str) -> Decimal:
    value = _require_text(row, field)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} 需要是数字") from exc


def _optional_decimal(row: dict[str, str], field: str) -> Decimal | None:
    value = _optional_text(row, field)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} 需要是数字") from exc


def _require_datetime(row: dict[str, str], field: str) -> datetime:
    value = _require_text(row, field)
    return _parse_datetime(field, value)


def _optional_datetime(row: dict[str, str], field: str) -> datetime | None:
    value = _optional_text(row, field)
    if value is None:
        return None
    return _parse_datetime(field, value)


def _optional_date(row: dict[str, str], field: str) -> date | None:
    value = _optional_text(row, field)
    if value is None:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} 日期格式必须是 YYYY-MM-DD")


def _parse_datetime(field: str, value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"{field} 时间格式必须是 YYYY-MM-DD HH:MM[:SS]")


def _merge_follow_up_customer_update(follow_up_customer_updates: dict[str, dict], insert_payload: dict):
    customer_id = insert_payload["customer_id"]
    existing = follow_up_customer_updates.get(customer_id)
    if existing and existing["occurred_at"] >= insert_payload["occurred_at"]:
        return
    follow_up_customer_updates[customer_id] = {
        "occurred_at": insert_payload["occurred_at"],
        "next_follow_up_at": insert_payload["next_follow_up_at"],
        "sentiment": insert_payload["sentiment"],
    }


def _apply_follow_up_customer_updates(db: Session, tenant_id: str, follow_up_customer_updates: dict[str, dict]):
    for customer_id, payload in follow_up_customer_updates.items():
        db.execute(
            text(
                """
                UPDATE crm_customer
                SET last_follow_up_at = :last_follow_up_at,
                    next_follow_up_at = :next_follow_up_at,
                    last_sentiment = :last_sentiment
                WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "last_follow_up_at": payload["occurred_at"],
                "next_follow_up_at": payload["next_follow_up_at"],
                "last_sentiment": payload["sentiment"],
            },
        )


def _build_failed_rows_csv(entity: str, failures: list[ImportFailure]) -> str | None:
    if not failures:
        return None

    output = io.StringIO()
    fieldnames = [*IMPORT_REQUIRED_FIELDS[entity], "error_reason"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for failure in failures:
        row = {field: failure.row_data.get(field, "") for field in IMPORT_REQUIRED_FIELDS[entity]}
        row["error_reason"] = failure.reason
        writer.writerow(row)
    return output.getvalue()
