from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.shared.backup_recovery import summarize_backup_recovery


def main() -> int:
    """中文注释：输出备份恢复策略清单；只读脚本，不执行真实备份、恢复或外部写入。"""

    plan = summarize_backup_recovery()
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["overall_status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
