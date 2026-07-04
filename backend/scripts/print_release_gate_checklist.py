from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.shared.release_gate import summarize_release_gate


def main() -> int:
    """中文注释：输出发布门禁清单；存在生产阻断时返回非 0，方便流水线拦截。"""

    checklist = summarize_release_gate()
    print(json.dumps(checklist, ensure_ascii=False, indent=2))
    return 1 if checklist["release_decision"] == "production_blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
