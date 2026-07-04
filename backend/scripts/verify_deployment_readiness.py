from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.shared.deployment_readiness import summarize_deployment_readiness


def main() -> int:
    """中文注释：部署启动前执行；存在阻断项时返回非 0，便于 CI/CD 或容器入口直接拦截。"""

    readiness = summarize_deployment_readiness(public=False)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 1 if readiness["overall_status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
