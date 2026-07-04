from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.shared.enterprise_hardening import summarize_enterprise_hardening


def main() -> int:
    """中文注释：输出企业级硬化阶段报告；只读脚本，不执行自动修复或外部动作。"""

    report = summarize_enterprise_hardening()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["overall_status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
