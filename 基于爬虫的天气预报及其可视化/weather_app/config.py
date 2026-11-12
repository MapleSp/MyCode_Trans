"""应用配置。"""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
INSTANCE_DIR = APP_DIR / "instance"
LOG_DIR = APP_DIR / "logs"
CITY_FILE = DATA_DIR / "city.txt"


class Config:
    """集中管理运行参数，环境变量可覆盖默认值。"""

    SECRET_KEY = os.getenv("WEATHER_SECRET_KEY", "atmos-local-weather-dashboard")
    JSON_AS_ASCII = False
    MAX_CONTENT_LENGTH = 64 * 1024

    CACHE_TTL_SECONDS = int(os.getenv("WEATHER_CACHE_TTL", "900"))
    STALE_TTL_HOURS = int(os.getenv("WEATHER_STALE_TTL_HOURS", "168"))
    HTTP_TIMEOUT_SECONDS = float(os.getenv("WEATHER_HTTP_TIMEOUT", "10"))
    HTTP_RETRIES = int(os.getenv("WEATHER_HTTP_RETRIES", "2"))
    QUEUE_WORKERS = int(os.getenv("WEATHER_QUEUE_WORKERS", "4"))
    QUEUE_CAPACITY = int(os.getenv("WEATHER_QUEUE_CAPACITY", "32"))
    QUEUE_WAIT_SECONDS = float(os.getenv("WEATHER_QUEUE_WAIT", "24"))

    WEATHER_RATE_LIMIT = int(os.getenv("WEATHER_RATE_LIMIT", "30"))
    SEARCH_RATE_LIMIT = int(os.getenv("SEARCH_RATE_LIMIT", "120"))
    LOCATION_RATE_LIMIT = int(os.getenv("LOCATION_RATE_LIMIT", "20"))
    RATE_WINDOW_SECONDS = 60
    DATABASE_PATH = os.getenv("WEATHER_DATABASE_PATH")


class TestConfig(Config):
    """测试环境配置。"""

    TESTING = True
    CACHE_TTL_SECONDS = 1
    HTTP_TIMEOUT_SECONDS = 1
    HTTP_RETRIES = 0
    QUEUE_WAIT_SECONDS = 2
