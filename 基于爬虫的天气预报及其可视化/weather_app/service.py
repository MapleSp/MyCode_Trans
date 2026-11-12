"""天气业务编排与多级缓存策略。"""

from __future__ import annotations

import copy
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from .advisor import WeatherAdvisor
from .cache import TTLCache
from .cities import CityResolver
from .database import WeatherDatabase
from .queue import WeatherTaskQueue
from .scraper import DemoWeatherProvider, WeatherScraper


LOGGER = logging.getLogger(__name__)
CHINA_TIMEZONE = timezone(timedelta(hours=8))


class WeatherService:
    """串联缓存、数据库、并发抓取与智能分析。"""

    def __init__(
        self,
        *,
        resolver: CityResolver,
        database: WeatherDatabase,
        cache: TTLCache,
        queue: WeatherTaskQueue,
        scraper: WeatherScraper,
        demo: DemoWeatherProvider,
        advisor: WeatherAdvisor,
        cache_ttl: int = 900,
        stale_hours: int = 168,
        queue_wait: float = 24,
    ) -> None:
        self.resolver = resolver
        self.database = database
        self.cache = cache
        self.queue = queue
        self.scraper = scraper
        self.demo = demo
        self.advisor = advisor
        self.cache_ttl = cache_ttl
        self.stale_hours = stale_hours
        self.queue_wait = queue_wait

    def get_weather(self, query: str, *, client_key: str = "anonymous") -> dict[str, Any]:
        city = self.resolver.resolve(query)
        cache_key = f"weather:{city.code}"

        cached = self.cache.get(cache_key)
        if cached:
            payload = self._finalize(copy.deepcopy(cached), cache_layer="memory", stale=False)
            return payload

        snapshot = self.database.get_snapshot(city.code, max_age_hours=self.stale_hours)
        if snapshot and snapshot.get("_snapshot", {}).get("fresh"):
            snapshot_copy = copy.deepcopy(snapshot)
            snapshot_copy.pop("_snapshot", None)
            self.cache.set(cache_key, snapshot_copy, ttl=self.cache_ttl)
            self._record_search(query, city.name, city.code, client_key)
            return self._finalize(snapshot_copy, cache_layer="sqlite", stale=False)

        try:
            payload, coalesced = self.queue.run(
                cache_key,
                lambda: self.scraper.fetch(city),
                timeout=self.queue_wait,
            )
            self.cache.set(cache_key, copy.deepcopy(payload), ttl=self.cache_ttl)
            try:
                self.database.save_snapshot(
                    city.name,
                    city.code,
                    payload,
                    ttl_seconds=self.cache_ttl,
                    source=payload.get("meta", {}).get("source", "中国天气网"),
                )
            except Exception:
                LOGGER.exception("天气快照持久化失败 city=%s", city.name)
            self._record_search(query, city.name, city.code, client_key)
            result = self._finalize(payload, cache_layer="live", stale=False)
            result["meta"]["coalesced"] = coalesced
            return result
        except Exception as exc:
            LOGGER.warning("在线天气抓取失败 city=%s error=%s", city.name, exc)
            if snapshot:
                stale_payload = copy.deepcopy(snapshot)
                stale_meta = stale_payload.pop("_snapshot", {})
                self._record_search(query, city.name, city.code, client_key)
                result = self._finalize(
                    stale_payload,
                    cache_layer="sqlite-stale",
                    stale=True,
                    fallback_reason=str(exc),
                )
                result["meta"]["snapshot_fetched_at"] = stale_meta.get("fetched_at")
                return result

            demo_payload = self.demo.build(city, reason=str(exc))
            self._record_search(query, city.name, city.code, client_key)
            return self._finalize(demo_payload, cache_layer="demo", stale=True)

    def get_many(self, queries: list[str], *, client_key: str = "anonymous") -> list[dict[str, Any]]:
        """并行准备多个城市，演示队列与批处理能力。"""

        selected = queries[:4]
        with ThreadPoolExecutor(max_workers=max(1, len(selected))) as executor:
            futures = [
                executor.submit(self.get_weather, query, client_key=client_key)
                for query in selected
            ]
            return [future.result() for future in futures]

    def _finalize(
        self,
        payload: dict[str, Any],
        *,
        cache_layer: str,
        stale: bool,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(CHINA_TIMEZONE)
        payload["advice"] = self.advisor.analyze(payload)
        meta = payload.setdefault("meta", {})
        meta["cache_layer"] = cache_layer
        meta["is_stale"] = stale
        meta["served_at"] = now.isoformat(timespec="seconds")
        meta["expires_at"] = (now + timedelta(seconds=self.cache_ttl)).isoformat(timespec="seconds")
        if fallback_reason:
            meta["fallback_reason"] = fallback_reason
        payload["data_quality"] = self._data_quality(payload)
        return payload

    @staticmethod
    def _data_quality(payload: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current") or {}
        important_fields = (
            "temperature",
            "feels_like",
            "humidity",
            "wind_direction",
            "pressure_hpa",
            "visibility_km",
            "aqi",
        )
        valid = sum(1 for field in important_fields if current.get(field) not in (None, "", "暂无"))
        percent = round(valid / len(important_fields) * 100)
        return {
            "score": percent,
            "label": "完整" if percent >= 85 else ("较完整" if percent >= 60 else "部分缺失"),
            "forecast_days": len(payload.get("forecast") or []),
        }

    def _record_search(
        self,
        query: str,
        city_name: str,
        city_code: str,
        client_key: str,
    ) -> None:
        try:
            self.database.add_search(query, city_name, city_code, client_key)
        except Exception:
            LOGGER.exception("查询记录写入失败 city=%s", city_name)
