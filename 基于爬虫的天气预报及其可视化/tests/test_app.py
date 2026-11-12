"""核心功能自动化测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weather_app.advisor import WeatherAdvisor
from weather_app.cities import CityResolver
from weather_app.config import CITY_FILE
from weather_app.database import WeatherDatabase
from weather_app.factory import create_app
from weather_app.scraper import WeatherScraper


def sample_payload(city: str = "北京") -> dict:
    payload = {
        "city": {"name": city, "code": "101010100"},
        "current": {
            "city_name": city,
            "temperature": 36,
            "temperature_high": 38,
            "temperature_low": 27,
            "feels_like": 39,
            "weather": "晴",
            "humidity": 82,
            "wind_direction": "南风",
            "wind_level": "4级",
            "wind_speed_kmh": 22,
            "pressure_hpa": 1004,
            "visibility_km": 12,
            "rainfall_mm": 0,
            "rainfall_24h_mm": 0,
            "aqi": 112,
            "pm25": 78,
            "air_quality": {"level": "轻度污染", "score": 112, "pm25": 78, "color": "fair"},
            "observed_at": "2026-07-21T14:00:00+08:00",
            "is_day": True,
            "icon": "sun",
        },
        "forecast": [
            {
                "date": "2026-07-21",
                "date_label": "今天",
                "weekday": "周二",
                "weather": "晴",
                "temperature_high": 38,
                "temperature_low": 27,
                "wind_direction": "南风",
                "wind_level": "4级",
                "icon": "sun",
                "is_today": True,
            },
            {
                "date": "2026-07-22",
                "date_label": "明天",
                "weekday": "周三",
                "weather": "雷阵雨",
                "temperature_high": 32,
                "temperature_low": 25,
                "wind_direction": "东南风",
                "wind_level": "3级",
                "icon": "rain",
                "is_today": False,
            },
        ],
        "indices": [
            {
                "key": "uv",
                "name": "紫外线强度指数",
                "hint": "很强",
                "description": "避免长时间暴晒。",
                "tone": "warm",
            }
        ],
        "alerts": [],
        "meta": {
            "source": "测试数据",
            "source_url": "",
            "fetched_at": "2026-07-21T14:00:00+08:00",
            "updated_at": "2026-07-21T14:00:00+08:00",
            "mode": "live",
            "warnings": [],
        },
    }
    payload["advice"] = WeatherAdvisor().analyze(payload)
    return payload


class FakeWeatherService:
    def get_weather(self, query: str, *, client_key: str = "anonymous") -> dict:
        payload = sample_payload(query)
        payload["meta"]["cache_layer"] = "live"
        payload["meta"]["is_stale"] = False
        payload["data_quality"] = {"score": 100, "label": "完整", "forecast_days": 2}
        return payload

    def get_many(self, queries: list[str], *, client_key: str = "anonymous") -> list[dict]:
        return [self.get_weather(query, client_key=client_key) for query in queries]


class CityResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = CityResolver(CITY_FILE)

    def test_exact_and_suffix(self) -> None:
        self.assertEqual(self.resolver.resolve("北京市").name, "北京")
        self.assertEqual(self.resolver.resolve("海淀区").name, "海淀")

    def test_typo_and_pinyin(self) -> None:
        self.assertEqual(self.resolver.resolve("北就").name, "北京")
        self.assertEqual(self.resolver.resolve("shanghai").name, "上海")

    def test_suggestions_are_limited(self) -> None:
        suggestions = self.resolver.suggestions("北", limit=5)
        self.assertLessEqual(len(suggestions), 5)
        self.assertEqual(suggestions[0]["name"], "北京")


class AdvisorTests(unittest.TestCase):
    def test_hot_weather_contains_heat_and_uv_advice(self) -> None:
        advice = WeatherAdvisor().analyze(sample_payload())
        titles = {item["title"] for item in advice["recommendations"]}
        self.assertIn("注意避暑", titles)
        self.assertIn("做好防晒", titles)
        self.assertIn("随身带伞", titles)
        self.assertLess(advice["comfort_score"], 82)
        self.assertIn("今日区间 27—38℃", advice["summary"])

    def test_cold_weather_contains_warmth_advice(self) -> None:
        payload = sample_payload()
        payload["current"].update({"temperature": 3, "feels_like": 0, "weather": "晴"})
        payload["forecast"][0].update({"temperature_high": 6, "temperature_low": -2})
        payload["forecast"][1].update({"weather": "晴", "temperature_high": 8, "temperature_low": -1})
        advice = WeatherAdvisor().analyze(payload)
        titles = {item["title"] for item in advice["recommendations"]}
        self.assertIn("保暖", titles)


class ScraperParserTests(unittest.TestCase):
    def test_first_day_without_month_uses_update_month(self) -> None:
        html = """
        <html><body>
        <input id="fc_24h_internal_update_time" value="2026111220">
        <div id="7d"><ul>
          <li>
            <h1>12日（今天）</h1><p class="wea">晴</p>
            <p class="tem"><i>1℃</i></p>
            <p class="win"><em><span title="北风"></span></em><i>&lt;3级</i></p>
          </li>
        </ul></div></body></html>
        """
        rich = {
            "fc": {
                "f": [
                    {"fi": "11/12", "fc": "15", "fd": "1", "fe": "北风", "fg": "<3级"}
                ]
            }
        }
        result = WeatherScraper()._parse_forecast(html, rich, "北京")
        self.assertEqual(result[0]["date"], "2026-11-12")
        self.assertEqual(result[0]["temperature_high"], 15)
        self.assertEqual(result[0]["weekday"], "周四")


class DatabaseTests(unittest.TestCase):
    def test_snapshot_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = WeatherDatabase(Path(temp_dir) / "weather.db")
            database.initialize()
            payload = {"city": {"name": "北京"}, "current": {"temperature": 12}}
            database.save_snapshot("北京", "101010100", payload, ttl_seconds=60, source="测试")
            loaded = database.get_snapshot("101010100")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["current"]["temperature"], 12)
            self.assertTrue(loaded["_snapshot"]["fresh"])


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "weather.db"),
                "SEARCH_RATE_LIMIT": 20,
                "WEATHER_RATE_LIMIT": 20,
                "LOCATION_RATE_LIMIT": 20,
            }
        )
        self.app.extensions["weather_service"] = FakeWeatherService()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pages_and_weather_api(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/weather.html?city=北京").status_code, 200)
        response = self.client.get("/api/weather/北京")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["city"]["name"], "北京")
        self.assertIn("advice", data)

    def test_city_suggestions_and_error_schema(self) -> None:
        response = self.client.get("/api/cities?query=北就")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["suggestions"][0]["name"], "北京")
        missing = self.client.get("/api/not-an-endpoint")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()["error"]["code"], "ENDPOINT_NOT_FOUND")

    def test_bad_location_is_rejected(self) -> None:
        response = self.client.get("/api/location?lat=abc&lon=116")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_COORDINATE")

    def test_api_rate_limit(self) -> None:
        self.app.config["SEARCH_RATE_LIMIT"] = 1
        headers = {"X-Client-ID": "rate-test-client"}
        first = self.client.get("/api/cities?query=北京", headers=headers)
        second = self.client.get("/api/cities?query=上海", headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.get_json()["error"]["code"], "RATE_LIMITED")


if __name__ == "__main__":
    unittest.main()
