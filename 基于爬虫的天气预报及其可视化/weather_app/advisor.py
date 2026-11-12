"""基于气象指标的智能建议引擎。"""

from __future__ import annotations

import re
from typing import Any


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class WeatherAdvisor:
    """用可解释的规则组合官方指数，输出生活建议。"""

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current") or {}
        forecast = payload.get("forecast") or []
        indices = payload.get("indices") or []

        temperature = _number(current.get("temperature"))
        feels_like = _number(current.get("feels_like"))
        humidity = _number(current.get("humidity"))
        wind_speed = _number(current.get("wind_speed_kmh"))
        wind_level = self._wind_number(current.get("wind_level"))
        aqi = _number((current.get("air_quality") or {}).get("score"))
        visibility = _number(current.get("visibility_km"))
        uv = self._find_index(indices, ("紫外线", "防晒"))
        rain_forecast = any("雨" in str(day.get("weather", "")) for day in forecast)
        # 今日区间只取当天预报，避免把未来几天的极端低温误写成今天温度。
        max_high = (
            _number(forecast[0].get("temperature_high")) if forecast else None
        ) or _number(current.get("temperature_high")) or temperature
        min_low = (
            _number(forecast[0].get("temperature_low")) if forecast else None
        ) or _number(current.get("temperature_low")) or temperature

        factors: list[dict[str, Any]] = []
        score = 100

        if temperature is not None and temperature <= 8:
            penalty = min(24, 12 + (8 - temperature) * 1.8)
            score -= penalty
            factors.append(self._factor("cold", "保暖优先", "体感偏冷，分层穿衣更从容。"))
        elif temperature is not None and temperature >= 31:
            penalty = min(25, 12 + (temperature - 30) * 2)
            score -= penalty
            factors.append(self._factor("heat", "暑热明显", "体感温度较高，需要补水与降温。"))

        if max_high is not None and max_high - (min_low or max_high) >= 10:
            score -= 6
            factors.append(self._factor("temperature", "昼夜温差大", "早晚与午间体感差异明显。"))

        if humidity is not None and humidity >= 80:
            score -= 8 if (temperature or 20) < 28 else 13
            factors.append(self._factor("humidity", "空气潮湿", "高湿度会放大闷热或阴冷感。"))
        elif humidity is not None and humidity <= 30:
            score -= 6
            factors.append(self._factor("dry", "空气偏干", "注意补水，并减少皮肤水分流失。"))

        uv_level = self._uv_level(uv)
        if uv_level >= 6:
            score -= 8
            factors.append(self._factor("uv", "紫外线较强", "午间外出建议使用 SPF30+ 防晒。"))

        if rain_forecast:
            score -= 10
            factors.append(self._factor("rain", "降水可能", "未来七天存在降雨，雨具应随手携带。"))

        if (wind_level is not None and wind_level >= 5) or (wind_speed is not None and wind_speed >= 29):
            score -= 8
            factors.append(self._factor("wind", "风力较大", "注意固定帽子与轻便物品。"))

        if aqi is not None and aqi > 100:
            score -= min(22, 8 + (aqi - 100) * 0.05)
            factors.append(self._factor("air", "空气质量需关注", "敏感人群应缩短高强度户外活动。"))

        if visibility is not None and visibility < 5:
            score -= 6
            factors.append(self._factor("visibility", "能见度偏低", "驾车请降低速度并保持车距。"))

        score = int(max(25, min(98, round(score))))
        recommendations = self._recommendations(
            temperature=temperature,
            feels_like=feels_like,
            humidity=humidity,
            uv=uv,
            uv_level=uv_level,
            rain_forecast=rain_forecast,
            wind_level=wind_level,
            aqi=aqi,
            min_low=min_low,
            max_high=max_high,
        )
        headline, summary = self._summary(
            temperature=temperature,
            max_high=max_high,
            min_low=min_low,
            humidity=humidity,
            uv_level=uv_level,
            rain_forecast=rain_forecast,
            aqi=aqi,
            factors=factors,
        )

        return {
            "headline": headline,
            "summary": summary,
            "risk_level": self._risk_level(score),
            "comfort_score": score,
            "weather_mood": self._weather_mood(current.get("weather", ""), score),
            "factors": factors,
            "recommendations": recommendations,
            "outfit": self._outfit_advice(temperature, min_low, max_high, wind_level, rain_forecast),
            "activity": self._activity_advice(temperature, aqi, rain_forecast, uv_level),
            "trend": self._trend_advice(forecast, rain_forecast),
            "best_window": self._best_window(max_high, min_low, rain_forecast, uv_level),
        }

    @staticmethod
    def _factor(key: str, title: str, detail: str) -> dict[str, str]:
        return {"key": key, "title": title, "detail": detail}

    @staticmethod
    def _find_index(indices: list[dict[str, Any]], names: tuple[str, ...]) -> dict[str, Any] | None:
        for index in indices:
            if any(name in str(index.get("name", "")) for name in names):
                return index
        return None

    @staticmethod
    def _uv_level(index: dict[str, Any] | None) -> int:
        if not index:
            return 0
        hint = str(index.get("hint", ""))
        if any(word in hint for word in ("极强", "很强", "最强")):
            return 9
        if "强" in hint:
            return 7
        if "中等" in hint:
            return 5
        if any(word in hint for word in ("弱", "低")):
            return 3
        match = re.search(r"\d+", hint)
        return int(match.group()) if match else 4

    @staticmethod
    def _wind_number(value: Any) -> float | None:
        match = re.search(r"\d+(?:-\d+)?", str(value or ""))
        if not match:
            return None
        parts = [float(part) for part in match.group().split("-")]
        return sum(parts) / len(parts)

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 82:
            return "舒适"
        if score >= 65:
            return "留意"
        if score >= 48:
            return "需防护"
        return "重点防护"

    @staticmethod
    def _weather_mood(weather: str, score: int) -> str:
        if "晴" in weather:
            return "晴朗 · 适合舒展"
        if "雨" in weather:
            return "湿润 · 慢一点出门"
        if "雪" in weather:
            return "雪意 · 注意脚下"
        if any(word in weather for word in ("雾", "霾")):
            return "朦胧 · 减少久留"
        if score >= 82:
            return "平和 · 适合外出"
        return "多变 · 做好准备"

    def _recommendations(
        self,
        *,
        temperature: float | None,
        feels_like: float | None,
        humidity: float | None,
        uv: dict[str, Any] | None,
        uv_level: int,
        rain_forecast: bool,
        wind_level: float | None,
        aqi: float | None,
        min_low: float | None,
        max_high: float | None,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        basis_temp = feels_like if feels_like is not None else temperature

        if basis_temp is not None and basis_temp <= 10:
            items.append(
                self._recommendation(
                    "保暖",
                    "采用“薄内搭 + 保暖中层 + 防风外套”的分层穿法，重点护住颈部与脚踝。",
                    "warm",
                    "high",
                    "coat",
                )
            )
        elif basis_temp is not None and basis_temp <= 18:
            items.append(
                self._recommendation(
                    "轻外套",
                    "体感微凉，早晚加一件针织衫或薄风衣，午间方便脱卸。",
                    "cool",
                    "medium",
                    "jacket",
                )
            )
        elif basis_temp is not None and basis_temp >= 30:
            items.append(
                self._recommendation(
                    "注意避暑",
                    "优先选择透气浅色衣物，少量多次补水，避免长时间暴晒。",
                    "heat",
                    "high",
                    "sun",
                )
            )

        if uv_level >= 6:
            items.append(
                self._recommendation(
                    "做好防晒",
                    f"紫外线指数为“{uv.get('hint') if uv else '较强'}”，建议 SPF30+、遮阳帽与墨镜配合使用。",
                    "sun",
                    "high",
                    "sunscreen",
                )
            )
        elif uv_level >= 4:
            items.append(
                self._recommendation(
                    "基础防晒",
                    "午间外出涂抹防晒霜，长时间户外活动可增加遮阳措施。",
                    "warm",
                    "medium",
                    "sunscreen",
                )
            )

        if rain_forecast:
            items.append(
                self._recommendation(
                    "随身带伞",
                    "未来几天有降水信号，建议携带轻便雨伞，并为电子设备准备防水收纳。",
                    "rain",
                    "high",
                    "umbrella",
                )
            )

        if wind_level is not None and wind_level >= 4:
            items.append(
                self._recommendation(
                    "注意防风",
                    "风力偏大，骑行与步行经过开阔路段时注意侧风，固定好轻便物品。",
                    "wind",
                    "medium",
                    "wind",
                )
            )

        if humidity is not None and humidity >= 80:
            items.append(
                self._recommendation(
                    "保持干爽",
                    "湿度较高，选择速干面料并保持室内通风，空调除湿不宜过冷。",
                    "humidity",
                    "medium",
                    "drop",
                )
            )
        elif humidity is not None and humidity <= 30:
            items.append(
                self._recommendation(
                    "及时补水",
                    "空气偏干，增加饮水量并使用润肤产品，室内可适度加湿。",
                    "dry",
                    "medium",
                    "water",
                )
            )

        if aqi is not None and aqi > 100:
            items.append(
                self._recommendation(
                    "关注空气",
                    f"空气质量指数为 {int(aqi)}，敏感人群建议减少高强度户外运动并佩戴口罩。",
                    "air",
                    "high",
                    "mask",
                )
            )

        if len(items) < 4:
            items.append(
                self._recommendation(
                    "舒适出行",
                    "天气整体平稳，适合通勤与轻量户外活动，仍记得关注临近预报。",
                    "green",
                    "low",
                    "walk",
                )
            )
        if max_high is not None and min_low is not None and max_high - min_low >= 9:
            items.append(
                self._recommendation(
                    "应对温差",
                    "今日昼夜温差较大，可携带可折叠外套，儿童与老人更要注意早晚保暖。",
                    "cool",
                    "medium",
                    "layers",
                )
            )
        return items[:7]

    @staticmethod
    def _recommendation(
        title: str,
        text: str,
        tone: str,
        priority: str,
        icon: str,
    ) -> dict[str, str]:
        return {
            "title": title,
            "text": text,
            "tone": tone,
            "priority": priority,
            "icon": icon,
        }

    @staticmethod
    def _summary(
        *,
        temperature: float | None,
        max_high: float | None,
        min_low: float | None,
        humidity: float | None,
        uv_level: int,
        rain_forecast: bool,
        aqi: float | None,
        factors: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if factors:
            headline = factors[0]["title"] + "，" + factors[1]["title"] if len(factors) > 1 else factors[0]["title"]
        elif temperature is not None and 18 <= temperature <= 28:
            headline = "天气从容，适合安排今天"
        else:
            headline = "天气平稳，出门前再看一眼天空"

        parts = []
        if temperature is not None:
            parts.append(f"当前约 {round(temperature)}℃")
        if max_high is not None and min_low is not None:
            parts.append(f"今日区间 {round(min_low)}—{round(max_high)}℃")
        if humidity is not None:
            parts.append(f"湿度 {round(humidity)}%")
        if rain_forecast:
            parts.append("未来几日有降水可能")
        if uv_level >= 6:
            parts.append("紫外线需要重点关注")
        if aqi is not None and aqi > 100:
            parts.append("空气质量对敏感人群不够友好")
        if not parts:
            parts.append("暂无完整观测值，请以官方临近预报为准")
        return headline, "，".join(parts) + "。"

    @staticmethod
    def _outfit_advice(
        temperature: float | None,
        min_low: float | None,
        max_high: float | None,
        wind_level: float | None,
        rain_forecast: bool,
    ) -> str:
        base = temperature if temperature is not None else 20
        if base <= 5:
            layers = "羽绒或厚大衣、羊毛衫与长裤"
        elif base <= 12:
            layers = "大衣、毛衣与保暖长裤"
        elif base <= 18:
            layers = "薄外套、针织衫与长裤"
        elif base <= 25:
            layers = "衬衫、轻外套与舒适长裤"
        elif base <= 30:
            layers = "短袖、薄长裤或裙装"
        else:
            layers = "透气短袖、轻薄下装与遮阳帽"
        extras = []
        if wind_level is not None and wind_level >= 4:
            extras.append("优先选择防风面料")
        if rain_forecast:
            extras.append("鞋子注意防滑")
        if max_high is not None and min_low is not None and max_high - min_low >= 9:
            extras.append("用可穿脱的外套应对温差")
        return f"建议选择{layers}；" + "，".join(extras) + "。" if extras else f"建议选择{layers}。"

    @staticmethod
    def _activity_advice(
        temperature: float | None,
        aqi: float | None,
        rain_forecast: bool,
        uv_level: int,
    ) -> str:
        if aqi is not None and aqi > 150:
            return "建议改为室内轻量运动，并减少开窗时长。"
        if temperature is not None and (temperature >= 33 or temperature <= -5):
            return "户外运动强度不宜过高，可选择室内活动。"
        if rain_forecast:
            return "优先安排室内活动；若外出，注意湿滑路面与鞋底抓地。"
        if uv_level >= 7:
            return "适合清晨或傍晚活动，午间减少连续暴晒。"
        return "适合散步、慢跑或骑行，运动前后注意补水与拉伸。"

    @staticmethod
    def _trend_advice(forecast: list[dict[str, Any]], rain_forecast: bool) -> str:
        if len(forecast) < 2:
            return "暂无足够数据判断未来趋势。"
        first_high = _number(forecast[0].get("temperature_high"))
        last_high = _number(forecast[-1].get("temperature_high"))
        if first_high is None or last_high is None:
            return "未来几天天气存在波动，建议关注最新预报。"
        delta = last_high - first_high
        if delta >= 4:
            trend = "整体升温"
        elif delta <= -4:
            trend = "逐步降温"
        else:
            trend = "气温相对平稳"
        rain_text = "期间有降水信号" if rain_forecast else "暂未看到明显降水信号"
        return f"未来七天{trend}，{rain_text}。"

    @staticmethod
    def _best_window(
        max_high: float | None,
        min_low: float | None,
        rain_forecast: bool,
        uv_level: int,
    ) -> str:
        if rain_forecast:
            return "建议出门前查看分钟级降水；雨间歇更适合短时出行。"
        if max_high is not None and max_high >= 30 or uv_level >= 7:
            return "相对舒适的外出窗口：07:00—10:00 或 17:00 以后。"
        if min_low is not None and min_low <= 5:
            return "相对舒适的外出窗口：10:00—15:00，早晚注意保暖。"
        return "相对舒适的外出窗口：09:00—16:00。"
