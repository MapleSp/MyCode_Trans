"""Flask 应用工厂。"""

from __future__ import annotations

import logging
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask, g, request

from .advisor import WeatherAdvisor
from .cache import TTLCache
from .cities import CityResolver
from .config import CITY_FILE, INSTANCE_DIR, LOG_DIR, Config
from .database import WeatherDatabase
from .location import LocationResolver
from .queue import WeatherTaskQueue
from .rate_limit import RateLimiter
from .routes import bp, register_error_handlers
from .scraper import DemoWeatherProvider, WeatherScraper
from .service import WeatherService


def _configure_logging(app: Flask) -> None:
    if app.testing:
        app.logger.setLevel(logging.CRITICAL)
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    file_handler = RotatingFileHandler(
        LOG_DIR / "weather.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
        app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
        static_url_path="/static",
    )
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    app.json.ensure_ascii = False
    _configure_logging(app)

    resolver = CityResolver(CITY_FILE)
    database = WeatherDatabase(app.config.get("DATABASE_PATH") or INSTANCE_DIR / "weather.db")
    database.initialize()
    cache = TTLCache(default_ttl=app.config["CACHE_TTL_SECONDS"])
    queue = WeatherTaskQueue(
        workers=app.config["QUEUE_WORKERS"],
        capacity=app.config["QUEUE_CAPACITY"],
    )
    scraper = WeatherScraper(
        timeout=app.config["HTTP_TIMEOUT_SECONDS"],
        retries=app.config["HTTP_RETRIES"],
    )
    service = WeatherService(
        resolver=resolver,
        database=database,
        cache=cache,
        queue=queue,
        scraper=scraper,
        demo=DemoWeatherProvider(),
        advisor=WeatherAdvisor(),
        cache_ttl=app.config["CACHE_TTL_SECONDS"],
        stale_hours=app.config["STALE_TTL_HOURS"],
        queue_wait=app.config["QUEUE_WAIT_SECONDS"],
    )
    limiter = RateLimiter(window_seconds=app.config["RATE_WINDOW_SECONDS"])

    app.extensions["city_resolver"] = resolver
    app.extensions["weather_database"] = database
    app.extensions["weather_cache"] = cache
    app.extensions["weather_queue"] = queue
    app.extensions["weather_scraper"] = scraper
    app.extensions["weather_service"] = service
    app.extensions["location_resolver"] = LocationResolver(
        resolver,
        timeout=min(6, app.config["HTTP_TIMEOUT_SECONDS"]),
    )
    app.extensions["rate_limiter"] = limiter

    app.register_blueprint(bp)
    register_error_handlers(app)

    @app.before_request
    def attach_request_id():
        request.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        g.request_started = True

    @app.after_request
    def request_headers(response):
        response.headers["X-Request-ID"] = getattr(request, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        elif request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app
