from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from app.shared.pilot_data_pack import summarize_pilot_data_pack

DEFAULT_TENANT_ID = "demo_tenant"


def main() -> int:
    """中文注释：只读输出试点数据包覆盖情况；不会修复 seed 或写入数据库。"""

    tenant_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TENANT_ID
    with SessionLocal() as db:
        pack = summarize_pilot_data_pack(db, tenant_id=tenant_id)
    print(json.dumps(pack, ensure_ascii=False, indent=2))
    return 0 if pack["overall_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
