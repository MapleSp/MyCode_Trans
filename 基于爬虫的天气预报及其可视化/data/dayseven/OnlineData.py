"""兼容旧启动入口，实际应用已迁移到模块化 weather_app 包。"""

import sys
from pathlib import Path

# 从旧的 data/dayseven 目录启动时，把项目根目录加入模块搜索路径。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
