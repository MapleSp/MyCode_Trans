"""中国天气网页面与实时数据接口解析。"""

from __future__ import annotations

import json
import logging
import math
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from .cities import City
from .errors import UpstreamError


LOGGER = logging.getLogger(__name__)
CHINA_TIMEZONE = timezone(timedelta(hours=8))


WEATHER_INDEX_URL = "https://d1.weather.com.cn/weather_index/{code}.html?_={timestamp}"
FORECAST_URL = "https://www.weather.com.cn/weather/{code}.shtml"

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", str(value).replace(",", ""))
    return int(match.group()) if match else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def _now_iso() -> str:
    return datetime.now(CHINA_TIMEZONE).isoformat(timespec="seconds")


class WeatherScraper:
    """抓取七日预报与官方实时生活指数。"""

    def __init__(self, *, timeout: float = 10, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)

    def fetch(self, city: City) -> dict[str, Any]:
        started_at = _now_iso()
        errors: list[str] = []

        rich_data: dict[str, Any] = {}
        html_text = ""
        try:
            rich_data = self._fetch_rich_data(city.code)
        except Exception as exc:  # 单项失败时继续尝试七日页面
            LOGGER.warning("实时指数抓取失败 city=%s error=%s", city.name, exc)
            errors.append(f"实时指数：{exc}")

        try:
            html_text = self._request_text(
                FORECAST_URL.format(code=city.code),
                referer="https://www.weather.com.cn/",
            )
        except Exception as exc:
            LOGGER.warning("七日预报抓取失败 city=%s error=%s", city.name, exc)
            errors.append(f"七日预报：{exc}")

        forecast = self._parse_forecast(html_text, rich_data, city.name) if html_text else []
        if not forecast:
            forecast = self._forecast_from_rich(rich_data, city.name)
        if not rich_data and not forecast:
            raise UpstreamError(
                "天气服务暂时不可用，正在尝试历史快照",
                details={"errors": errors},
            )

        current = self._parse_current(rich_data, forecast, city.name)
        indices = self._parse_indices(rich_data)
        alerts = self._parse_alerts(rich_data)

        if not current.get("weather") and forecast:
            current["weather"] = forecast[0].get("weather") or "天气信息暂缺"
            current["temperature_high"] = forecast[0].get("temperature_high")
            current["temperature_low"] = forecast[0].get("temperature_low")
            if current.get("temperature") is None:
                high = forecast[0].get("temperature_high")
                low = forecast[0].get("temperature_low")
                if high is not None and low is not None:
                    current["temperature"] = round((high + low) / 2, 1)

        return {
            "city": city.to_dict(),
            "current": current,
            "forecast": forecast[:7],
            "indices": indices,
            "alerts": alerts,
            "meta": {
                "source": "中国天气网",
                "source_url": FORECAST_URL.format(code=city.code),
                "fetched_at": started_at,
                "updated_at": current.get("observed_at") or started_at,
                "mode": "live",
                "warnings": errors,
            },
        }

    def _request_text(self, url: str, *, referer: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.get(
                    url,
                    headers={
                        "User-Agent": random.choice(USER_AGENTS),
                        "Referer": referer,
                        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                        "Cache-Control": "no-cache",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.content.decode("utf-8", errors="replace")
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.35 * (2**attempt) + random.uniform(0, 0.2))
        raise UpstreamError(f"请求上游天气页面失败：{last_error}")

    def _fetch_rich_data(self, city_code: str) -> dict[str, Any]:
        url = WEATHER_INDEX_URL.format(
            code=city_code,
            timestamp=int(time.time() * 1000),
        )
        text = self._request_text(url, referer=f"https://www.weather.com.cn/weather/{city_code}.shtml")
        variables = {
            name: self._extract_js_variable(text, name)
            for name in ("cityDZ", "alarmDZ", "dataSK", "dataZS", "fc")
        }
        if not variables["dataSK"] and not variables["fc"]:
            raise UpstreamError("实时天气数据格式无法识别")
        return {key: value for key, value in variables.items() if value is not None}

    @staticmethod
    def _extract_js_variable(text: str, name: str) -> Any:
        pattern = re.compile(rf"\bvar\s+{re.escape(name)}\s*=\s*")
        match = pattern.search(text)
        if not match:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(text, match.end())
            return value
        except (json.JSONDecodeError, ValueError):
            LOGGER.debug("JavaScript 变量解析失败 name=%s", name)
            return None

    def _parse_forecast(
        self,
        html_text: str,
        rich_data: dict[str, Any],
        city_name: str,
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html_text, "html.parser")
        container = soup.find("div", id="7d")
        if not container:
            LOGGER.warning("未找到七日预报容器 city=%s", city_name)
            return []

        update_node = soup.find("input", id="fc_24h_internal_update_time")
        update_value = update_node.get("value", "") if update_node else ""
        update_year, update_month = self._parse_update_month(update_value)
        rich_forecasts = self._rich_forecast_map(rich_data, update_year)

        result: list[dict[str, Any]] = []
        for index, day in enumerate(container.select("ul > li")):
            title_node = day.find("h1")
            weather_node = day.select_one("p.wea")
            temperature_node = day.select_one("p.tem")
            wind_node = day.select_one("p.win")
            if not title_node or not weather_node or not temperature_node:
                continue

            date_label = title_node.get_text(" ", strip=True)
            month, day_of_month = self._parse_day_month(date_label)
            effective_month = month or update_month
            year = update_year or datetime.now(CHINA_TIMEZONE).year
            if update_month == 12 and effective_month == 1:
                year += 1
            date_value = (
                f"{year:04d}-{effective_month:02d}-{day_of_month:02d}"
                if effective_month and day_of_month
                else date_label
            )
            rich_day = rich_forecasts.get((effective_month, day_of_month), {})

            high_node = temperature_node.find("span")
            low_node = temperature_node.find("i")
            high = _to_int(high_node.get_text()) if high_node else rich_day.get("high")
            low = _to_int(low_node.get_text()) if low_node else rich_day.get("low")

            wind_titles = [
                node.get("title", "").strip()
                for node in wind_node.select("span") if wind_node and node.get("title")
            ]
            wind_direction = "转".join(dict.fromkeys(wind_titles)) if wind_titles else rich_day.get("wind", "")
            wind_level_node = wind_node.find("i") if wind_node else None
            wind_level = (
                wind_level_node.get_text(" ", strip=True)
                if wind_level_node
                else rich_day.get("wind_level", "")
            )

            weather = weather_node.get_text(" ", strip=True)
            result.append(
                {
                    "date": date_value,
                    "date_label": self._friendly_date_label(date_label, date_value),
                    "weekday": (
                        self._extract_weekday(date_label)
                        or self._weekday_from_date(year, effective_month, day_of_month)
                    ),
                    "weather": weather,
                    "temperature_high": high,
                    "temperature_low": low,
                    "wind_direction": wind_direction or "暂无",
                    "wind_level": wind_level or "暂无",
                    "icon": self._weather_icon(weather),
                    "is_today": index == 0,
                }
            )
        return result

    def _forecast_from_rich(
        self,
        rich_data: dict[str, Any],
        city_name: str,
    ) -> list[dict[str, Any]]:
        raw_days = ((rich_data.get("fc") or {}).get("f") or [])
        if not isinstance(raw_days, list):
            return []
        result = []
        for index, item in enumerate(raw_days[:7]):
            date_text = str(item.get("fi", ""))
            month, day_of_month = self._parse_day_month(date_text)
            now = datetime.now(CHINA_TIMEZONE)
            year = now.year + (1 if now.month == 12 and month == 1 else 0)
            weather = "天气信息暂缺"
            result.append(
                {
                    "date": f"{year:04d}-{month:02d}-{day_of_month:02d}" if month and day_of_month else date_text,
                    "date_label": str(item.get("fj", date_text)),
                    "weekday": self._weekday_from_date(year, month, day_of_month),
                    "weather": weather,
                    "temperature_high": _to_int(item.get("fc")),
                    "temperature_low": _to_int(item.get("fd")),
                    "wind_direction": item.get("fe") or "暂无",
                    "wind_level": item.get("fg") or "暂无",
                    "icon": "cloud",
                    "is_today": index == 0,
                    "source_note": f"{city_name}实时接口",
                }
            )
        return result

    def _parse_current(
        self,
        rich_data: dict[str, Any],
        forecast: list[dict[str, Any]],
        city_name: str,
    ) -> dict[str, Any]:
        data_sk = rich_data.get("dataSK") or {}
        temp = _to_float(data_sk.get("temp"))
        if temp is not None and temp >= 900:
            temp = None
        humidity = _to_int(data_sk.get("SD") or data_sk.get("sd"))
        wind_speed = _to_float(data_sk.get("wse"))
        aqi = _to_int(data_sk.get("aqi"))
        weather = data_sk.get("weather") or data_sk.get("weathere") or ""
        temperature_high = forecast[0].get("temperature_high") if forecast else None
        temperature_low = forecast[0].get("temperature_low") if forecast else None
        feels_like = self._feels_like(temp, humidity, wind_speed)
        air_quality = self._air_quality(aqi, _to_int(data_sk.get("aqi_pm25")))

        return {
            "city_name": data_sk.get("cityname") or city_name,
            "temperature": temp,
            "temperature_high": temperature_high,
            "temperature_low": temperature_low,
            "feels_like": feels_like,
            "weather": weather or "天气信息暂缺",
            "humidity": humidity,
            "wind_direction": data_sk.get("WD") or "暂无",
            "wind_level": data_sk.get("WS") or "暂无",
            "wind_speed_kmh": wind_speed,
            "pressure_hpa": _to_int(data_sk.get("qy")),
            "visibility_km": _to_float(data_sk.get("njd")),
            "rainfall_mm": _to_float(data_sk.get("rain")),
            "rainfall_24h_mm": _to_float(data_sk.get("rain24h")),
            "aqi": aqi,
            "pm25": _to_int(data_sk.get("aqi_pm25")),
            "air_quality": air_quality,
            "observed_at": self._observed_at(data_sk),
            "is_day": self._is_daytime(data_sk.get("time")),
            "icon": self._weather_icon(weather),
        }

    @staticmethod
    def _parse_indices(rich_data: dict[str, Any]) -> list[dict[str, str]]:
        raw = (rich_data.get("dataZS") or {}).get("zs") or {}
        result = []
        for key, value in raw.items():
            if not key.endswith("_name"):
                continue
            prefix = key[: -len("_name")]
            name = str(value).strip()
            hint = str(raw.get(f"{prefix}_hint", "")).strip()
            description = str(raw.get(f"{prefix}_des_s", "")).strip()
            if not name:
                continue
            result.append(
                {
                    "key": prefix,
                    "name": name,
                    "hint": hint or "暂无",
                    "description": description or "暂无详细说明",
                    "tone": WeatherScraper._index_tone(name, hint),
                }
            )
        return result

    @staticmethod
    def _parse_alerts(rich_data: dict[str, Any]) -> list[dict[str, str]]:
        raw = (rich_data.get("alarmDZ") or {}).get("w") or []
        if not isinstance(raw, list):
            return []
        alerts = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = item.get("w") or item.get("title") or item.get("name")
            if title:
                alerts.append(
                    {
                        "title": str(title),
                        "level": str(item.get("l") or item.get("level") or "气象预警"),
                        "description": str(item.get("t") or item.get("description") or ""),
                    }
                )
        return alerts

    @staticmethod
    def _rich_forecast_map(rich_data: dict[str, Any], fallback_year: int) -> dict[tuple[int, int], dict[str, Any]]:
        result: dict[tuple[int, int], dict[str, Any]] = {}
        for item in ((rich_data.get("fc") or {}).get("f") or []):
            month, day = WeatherScraper._parse_day_month(str(item.get("fi", "")))
            if month and day:
                result[(month, day)] = {
                    "high": _to_int(item.get("fc")),
                    "low": _to_int(item.get("fd")),
                    "wind": item.get("fe"),
                    "wind_level": item.get("fg"),
                }
        return result

    @staticmethod
    def _parse_day_month(value: str) -> tuple[int | None, int | None]:
        match = re.search(r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})", value)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
        else:
            # 首页首日通常只写“12日（今天）”，月份由页面更新时间补足。
            day_only = re.search(r"(?:^|\D)(\d{1,2})日", value)
            if not day_only:
                return None, None
            month, day = None, int(day_only.group(1))
        if month is None:
            if 1 <= day <= 31:
                return None, day
            return None, None
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None, None
        return month, day

    @staticmethod
    def _parse_update_month(value: str) -> tuple[int | None, int | None]:
        match = re.match(r"(\d{4})(\d{2})", value or "")
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _extract_weekday(date_label: str) -> str:
        match = re.search(r"[（(]([^）)]+)[）)]", date_label)
        if not match:
            return ""
        value = match.group(1)
        return value if ("周" in value or "星期" in value) else ""

    @staticmethod
    def _friendly_date_label(raw: str, date_value: str) -> str:
        weekday = WeatherScraper._extract_weekday(raw)
        if "今天" in raw:
            return "今天"
        if "明天" in raw:
            return "明天"
        if "后天" in raw:
            return "后天"
        try:
            parsed = datetime.strptime(date_value, "%Y-%m-%d")
            return f"{parsed.month}月{parsed.day}日"
        except ValueError:
            return raw.replace("（", " · ").replace("）", "").replace("(", " · ").replace(")", "") or raw

    @staticmethod
    def _weekday_from_date(year: int, month: int | None, day: int | None) -> str:
        if not month or not day:
            return ""
        try:
            weekday_names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
            return weekday_names[datetime(year, month, day).weekday()]
        except ValueError:
            return ""

    @staticmethod
    def _weather_icon(weather: str) -> str:
        text = weather or ""
        if any(word in text for word in ("雷",)):
            return "thunder"
        if any(word in text for word in ("雪", "冰雹", "冻雨")):
            return "snow"
        if any(word in text for word in ("雨", "阵雨")):
            return "rain"
        if any(word in text for word in ("雾", "霾", "沙", "尘")):
            return "fog"
        if any(word in text for word in ("风",)):
            return "wind"
        if any(word in text for word in ("阴",)):
            return "overcast"
        if any(word in text for word in ("云",)):
            return "cloud"
        return "sun"

    @staticmethod
    def _feels_like(temp: float | None, humidity: int | None, wind_speed: float | None) -> float | None:
        if temp is None:
            return None
        result = temp
        humidity_value = humidity if humidity is not None else 50
        wind_value = wind_speed if wind_speed is not None else 0
        if temp >= 26:
            result += max(0, humidity_value - 45) * 0.035
        elif temp <= 10:
            result -= min(4.5, wind_value * 0.07)
        return round(result, 1)

    @staticmethod
    def _air_quality(aqi: int | None, pm25: int | None) -> dict[str, Any]:
        if aqi is None:
            return {"level": "未知", "score": None, "pm25": pm25, "color": "muted"}
        if aqi <= 50:
            level, color = "优", "excellent"
        elif aqi <= 100:
            level, color = "良", "good"
        elif aqi <= 150:
            level, color = "轻度污染", "fair"
        elif aqi <= 200:
            level, color = "中度污染", "poor"
        elif aqi <= 300:
            level, color = "重度污染", "bad"
        else:
            level, color = "严重污染", "severe"
        return {"level": level, "score": aqi, "pm25": pm25, "color": color}

    @staticmethod
    def _index_tone(name: str, hint: str) -> str:
        text = f"{name}{hint}"
        if any(word in text for word in ("紫外线", "防晒", "中暑", "热")):
            return "warm"
        if any(word in text for word in ("雨", "洗车", "晾晒")):
            return "rain"
        if any(word in text for word in ("感冒", "穿衣", "风寒", "空气")):
            return "cool"
        if any(word in text for word in ("运动", "旅游", "心情", "夜生活")):
            return "green"
        return "neutral"

    @staticmethod
    def _observed_at(data_sk: dict[str, Any]) -> str:
        date_text = str(data_sk.get("date", ""))
        time_text = str(data_sk.get("time", ""))
        month_day = re.search(r"(\d{1,2})月(\d{1,2})日", date_text)
        time_match = re.match(r"(\d{1,2}):(\d{2})", time_text)
        if not month_day or not time_match:
            return _now_iso()
        now = datetime.now(CHINA_TIMEZONE)
        month, day = int(month_day.group(1)), int(month_day.group(2))
        year = now.year
        if now.month == 1 and month == 12:
            year -= 1
        try:
            observed = datetime(
                year,
                month,
                day,
                int(time_match.group(1)),
                int(time_match.group(2)),
                tzinfo=CHINA_TIMEZONE,
            )
            return observed.isoformat(timespec="seconds")
        except ValueError:
            return _now_iso()

    @staticmethod
    def _is_daytime(time_text: Any) -> bool:
        match = re.match(r"(\d{1,2}):", str(time_text or ""))
        if not match:
            return 6 <= datetime.now(CHINA_TIMEZONE).hour < 18
        return 6 <= int(match.group(1)) < 18


class DemoWeatherProvider:
    """网络和数据库都不可用时，按城市与季节生成可信的演示数据。"""

    def build(self, city: City, reason: str = "上游服务不可用") -> dict[str, Any]:
        now = datetime.now(CHINA_TIMEZONE)
        seed = sum(ord(char) for char in city.code) + now.timetuple().tm_yday
        month = now.month
        if month in (12, 1, 2):
            base_temp, season_weather = 3, "晴间多云"
        elif month in (3, 4, 5):
            base_temp, season_weather = 18, "多云"
        elif month in (6, 7, 8):
            base_temp, season_weather = 29, "多云有阵雨"
        else:
            base_temp, season_weather = 17, "晴"
        temp = base_temp + seed % 7 - 3
        humidity = 42 + seed % 38
        high = temp + 5
        low = temp - 4
        forecasts = []
        weather_cycle = [season_weather, "晴间多云", "多云", "小雨", "阴", "晴", "多云"]
        for offset in range(7):
            date_value = now + timedelta(days=offset)
            weather = weather_cycle[(seed + offset) % len(weather_cycle)]
            forecasts.append(
                {
                    "date": date_value.strftime("%Y-%m-%d"),
                    "date_label": "今天" if offset == 0 else ("明天" if offset == 1 else f"{date_value.month}月{date_value.day}日"),
                    "weekday": ("周一", "周二", "周三", "周四", "周五", "周六", "周日")[date_value.weekday()],
                    "weather": weather,
                    "temperature_high": high + (offset % 3) - 1,
                    "temperature_low": low + (offset % 2),
                    "wind_direction": ("东南风", "北风", "西南风")[(seed + offset) % 3],
                    "wind_level": f"{2 + (offset % 3)}级",
                    "icon": WeatherScraper._weather_icon(weather),
                    "is_today": offset == 0,
                }
            )
        uv_hint = "中等" if 3 <= month <= 9 else "弱"
        return {
            "city": city.to_dict(),
            "current": {
                "city_name": city.name,
                "temperature": temp,
                "temperature_high": high,
                "temperature_low": low,
                "feels_like": temp + 1,
                "weather": season_weather,
                "humidity": humidity,
                "wind_direction": "东南风",
                "wind_level": f"{2 + seed % 3}级",
                "wind_speed_kmh": 7 + seed % 11,
                "pressure_hpa": 1008 + seed % 12,
                "visibility_km": 12 + seed % 10,
                "rainfall_mm": 0,
                "rainfall_24h_mm": 0,
                "aqi": 48 + seed % 54,
                "pm25": 30 + seed % 40,
                "air_quality": WeatherScraper._air_quality(48 + seed % 54, 30 + seed % 40),
                "observed_at": now.isoformat(timespec="seconds"),
                "is_day": 6 <= now.hour < 18,
                "icon": WeatherScraper._weather_icon(season_weather),
            },
            "forecast": forecasts,
            "indices": [
                {"key": "uv", "name": "紫外线强度指数", "hint": uv_hint, "description": "外出建议做好基础防晒。", "tone": "warm"},
                {"key": "ct", "name": "穿衣指数", "hint": "适宜", "description": "根据早晚温差灵活增减衣物。", "tone": "cool"},
                {"key": "yd", "name": "运动指数", "hint": "较适宜", "description": "适合轻量户外活动，注意补水。", "tone": "green"},
                {"key": "ys", "name": "雨伞指数", "hint": "建议携带", "description": "天气存在变化，随身带一把轻便雨伞。", "tone": "rain"},
            ],
            "alerts": [],
            "meta": {
                "source": "内置演示数据",
                "source_url": "",
                "fetched_at": now.isoformat(timespec="seconds"),
                "updated_at": now.isoformat(timespec="seconds"),
                "mode": "demo",
                "reason": reason,
                "warnings": [reason],
            },
        }
