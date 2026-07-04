from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from app.shared.pilot_acceptance_report import summarize_pilot_acceptance_report

DEFAULT_TENANT_ID = "demo_tenant"


def main() -> int:
    """中文注释：只读打印企业试点验收报告；blocked 返回非 0，便于流水线拦截。"""

    tenant_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TENANT_ID
    with SessionLocal() as db:
        report = summarize_pilot_acceptance_report(db, tenant_id=tenant_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["overall_status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
