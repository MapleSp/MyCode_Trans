"""页面路由与 JSON API。"""

from __future__ import annotations

import uuid
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from .errors import ApiError
from .rate_limit import rate_limited


bp = Blueprint("weather", __name__)


def _service():
    return current_app.extensions["weather_service"]


def _resolver():
    return current_app.extensions["city_resolver"]


def _client_key() -> str:
    return (
        request.headers.get("X-Client-ID")
        or request.cookies.get("atmos_client")
        or request.remote_addr
        or "anonymous"
    )[:100]


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/weather.html")
def weather_page():
    return render_template("weather.html")


@bp.get("/api/cities")
@rate_limited("cities", "SEARCH_RATE_LIMIT")
def cities():
    query = request.args.get("query", "").strip()
    if len(query) > 40:
        raise ApiError("搜索内容过长", code="QUERY_TOO_LONG", status_code=400)
    suggestions = _resolver().suggestions(query, limit=8)
    return jsonify(
        {
            "query": query,
            "count": len(suggestions),
            "suggestions": suggestions,
            "empty": not bool(suggestions),
        }
    )


@bp.get("/api/location")
@rate_limited("location", "LOCATION_RATE_LIMIT")
def locate():
    try:
        latitude = float(request.args.get("lat", ""))
        longitude = float(request.args.get("lon", ""))
    except ValueError as exc:
        raise ApiError(
            "缺少有效的定位坐标",
            code="INVALID_COORDINATE",
            status_code=400,
        ) from exc
    result = current_app.extensions["location_resolver"].resolve(latitude, longitude)
    return jsonify(result)


@bp.get("/api/weather/<path:city>")
@rate_limited("weather", "WEATHER_RATE_LIMIT")
def weather_by_path(city: str):
    payload = _service().get_weather(city, client_key=_client_key())
    return jsonify(payload)


@bp.get("/weather")
@rate_limited("weather", "WEATHER_RATE_LIMIT")
def weather_legacy(city: str):
    query = request.args.get("city", "").strip()
    if not query:
        raise ApiError("请提供城市名称", code="CITY_REQUIRED", status_code=400)
    payload = _service().get_weather(query, client_key=_client_key())
    return jsonify(payload)


@bp.get("/api/compare")
@rate_limited("compare", "WEATHER_RATE_LIMIT")
def compare_weather():
    raw_cities = request.args.get("cities", "")
    queries = [item.strip() for item in raw_cities.split(",") if item.strip()]
    if not 2 <= len(queries) <= 4:
        raise ApiError("请选择 2—4 个城市进行对比", code="INVALID_COMPARE", status_code=400)
    results = _service().get_many(queries, client_key=_client_key())
    return jsonify({"count": len(results), "cities": results})


@bp.get("/api/recent")
def recent():
    items = current_app.extensions["weather_database"].recent_searches(_client_key(), limit=6)
    return jsonify({"searches": items})


@bp.get("/api/health")
def health():
    database = current_app.extensions["weather_database"]
    queue = current_app.extensions["weather_queue"]
    cache = current_app.extensions["weather_cache"]
    database_ok = database.health()
    return (
        jsonify(
            {
                "status": "ok" if database_ok else "degraded",
                "request_id": getattr(request, "request_id", None),
                "database": database_ok,
                "cache_items": cache.size,
                "queue_pending": queue.pending,
                "city_count": current_app.extensions["city_resolver"].city_count,
            }
        ),
        200 if database_ok else 503,
    )


@bp.get("/api/meta")
def api_meta():
    return jsonify(
        {
            "name": "Atmos 智能气象台",
            "version": "2.0.0",
            "source": "中国天气网",
            "endpoints": {
                "cities": "/api/cities?query=北",
                "weather": "/api/weather/北京",
                "location": "/api/location?lat=39.9&lon=116.4",
                "health": "/api/health",
            },
        }
    )


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return (
            jsonify(
                {
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                    },
                    "request_id": getattr(request, "request_id", str(uuid.uuid4())),
                }
            ),
            error.status_code,
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "error": {
                            "code": "ENDPOINT_NOT_FOUND",
                            "message": "接口不存在",
                            "details": None,
                        },
                        "request_id": getattr(request, "request_id", None),
                    }
                ),
                404,
            )
        return render_template(
            "error.html",
            status_code=404,
            message="这页天气云图飘走了",
        ), 404

    @app.errorhandler(413)
    def handle_too_large(_error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": "请求内容过大",
                        "details": None,
                    }
                }
            ),
            413,
        )

    @app.errorhandler(500)
    def handle_server_error(error):
        app.logger.exception("未处理的服务端异常", exc_info=error)
        if request.path.startswith("/api/") or request.path == "/weather":
            return (
                jsonify(
                    {
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "服务暂时开小差了，请稍后重试",
                            "details": None,
                        },
                        "request_id": getattr(request, "request_id", None),
                    }
                ),
                500,
            )
        return render_template(
            "error.html",
            status_code=500,
            message="高空流暂时不稳定",
        ), 500

