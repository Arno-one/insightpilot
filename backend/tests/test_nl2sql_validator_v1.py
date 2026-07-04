from app.modules.nl2sql.sql_validator import ensure_limit, ensure_soft_delete_filters, validate_sql


def test_nl2sql_validator_accepts_safe_select_with_tenant_filter():
    sql = "SELECT customer_id FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 20"

    valid, error = validate_sql(sql)

    assert valid is True
    assert error == ""


def test_nl2sql_validator_rejects_dangerous_or_cross_tenant_sql():
    unsafe_cases = [
        "DELETE FROM crm_customer WHERE tenant_id = :tenant_id",
        "SELECT customer_id FROM crm_customer; DROP TABLE crm_customer",
        "SELECT customer_id FROM crm_customer",
        "UNSUPPORTED",
    ]

    for sql in unsafe_cases:
        valid, error = validate_sql(sql)
        assert valid is False
        assert error


def test_nl2sql_validator_injects_soft_delete_filter_before_order_and_limit():
    sql = "SELECT p.probe_id FROM nl2sql_probe p WHERE p.tenant_id = :tenant_id ORDER BY p.probe_id LIMIT 100"

    safe_sql = ensure_soft_delete_filters(sql, {"nl2sql_probe"})

    assert "p.is_deleted = 0" in safe_sql
    assert safe_sql.index("p.is_deleted = 0") < safe_sql.index("ORDER BY")
    assert safe_sql.endswith("LIMIT 100")


def test_nl2sql_validator_caps_limit_to_executor_max_rows():
    assert ensure_limit("SELECT id FROM demo WHERE tenant_id = :tenant_id", 100).endswith("LIMIT 100")
    assert ensure_limit("SELECT id FROM demo WHERE tenant_id = :tenant_id LIMIT 5000", 100).endswith("LIMIT 100")
