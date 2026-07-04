from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.shared.smoke_test_plan import summarize_smoke_test_plan


def main() -> int:
    """中文注释：输出企业试点冒烟测试计划；只读脚本，不执行任何测试步骤。"""

    plan = summarize_smoke_test_plan()
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0 if plan["overall_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
