from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from app.shared.pilot_operations_runbook import summarize_pilot_operations_runbook

DEFAULT_TENANT_ID = "demo_tenant"


def main() -> int:
    """中文注释：只读打印试点运营手册；存在 blocker 时返回非 0，便于试点前拦截。"""

    tenant_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TENANT_ID
    with SessionLocal() as db:
        runbook = summarize_pilot_operations_runbook(db, tenant_id=tenant_id)
    print(json.dumps(runbook, ensure_ascii=False, indent=2))
    return 0 if runbook["pilot_operable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
