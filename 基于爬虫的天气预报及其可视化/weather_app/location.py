"""浏览器定位结果反查城市。"""

from __future__ import annotations

import logging
import math
from typing import Any

import requests

from .cities import CityResolver
from .errors import ApiError


LOGGER = logging.getLogger(__name__)

# 离线兜底使用的省会及主要城市坐标。
MAJOR_CITY_COORDS = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "天津": (39.3434, 117.3616),
    "重庆": (29.5630, 106.5516),
    "石家庄": (38.0428, 114.5149),
    "太原": (37.8706, 112.5489),
    "呼和浩特": (40.8426, 111.7492),
    "沈阳": (41.8057, 123.4315),
    "长春": (43.8171, 125.3235),
    "哈尔滨": (45.8038, 126.5350),
    "南京": (32.0603, 118.7969),
    "杭州": (30.2741, 120.1551),
    "合肥": (31.8206, 117.2272),
    "福州": (26.0745, 119.2965),
    "南昌": (28.6820, 115.8579),
    "济南": (36.6512, 117.1201),
    "郑州": (34.7466, 113.6254),
    "武汉": (30.5928, 114.3055),
    "长沙": (28.2282, 112.9388),
    "广州": (23.1291, 113.2644),
    "南宁": (22.8170, 108.3665),
    "海口": (20.0440, 110.1999),
    "成都": (30.5728, 104.0668),
    "贵阳": (26.6470, 106.6302),
    "昆明": (25.0389, 102.7183),
    "拉萨": (29.6520, 91.1721),
    "西安": (34.3416, 108.9398),
    "兰州": (36.0611, 103.8343),
    "西宁": (36.6171, 101.7782),
    "银川": (38.4872, 106.2309),
    "乌鲁木齐": (43.8256, 87.6168),
    "深圳": (22.5431, 114.0579),
    "青岛": (36.0671, 120.3826),
    "大连": (38.9140, 121.6147),
    "厦门": (24.4798, 118.0894),
    "三亚": (18.2528, 109.5119),
    "香港": (22.3193, 114.1694),
    "澳门": (22.1987, 113.5439),
    "台北市": (25.0330, 121.5654),
}


class LocationResolver:
    """优先在线反查行政区，失败后返回最近的已知城市。"""

    def __init__(self, resolver: CityResolver, timeout: float = 6) -> None:
        self.resolver = resolver
        self.timeout = timeout

    def resolve(self, latitude: float, longitude: float) -> dict[str, Any]:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ApiError("定位坐标不合法", code="INVALID_COORDINATE", status_code=400)

        candidates: list[str] = []
        source = "nearest-city"
        try:
            response = requests.get(
                "https://api.bigdatacloud.net/data/reverse-geocode-client",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "localityLanguage": "zh",
                },
                headers={"User-Agent": "AtmosWeatherDashboard/2.0"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            source = "reverse-geocode"
            candidates.extend(
                [
                    data.get("city"),
                    data.get("locality"),
                    data.get("principalSubdivision"),
                ]
            )
            locality_info = data.get("localityInfo") or {}
            for item in locality_info.get("administrative") or []:
                if isinstance(item, dict):
                    candidates.append(item.get("name"))
            candidates = list(dict.fromkeys(name for name in candidates if name))
        except Exception as exc:
            LOGGER.warning("在线反查定位失败，改用最近城市：%s", exc)

        city = self.resolver.resolve_any(candidates)
        if not city:
            nearest_name, distance = self._nearest_city(latitude, longitude)
            city = self.resolver.resolve(nearest_name)
            source = f"nearest-city:{round(distance)}km"

        return {
            "city": city.to_dict(),
            "coordinates": {"latitude": latitude, "longitude": longitude},
            "source": source,
            "candidates": candidates[:6],
            "message": f"已定位至{city.name}附近",
        }

    @staticmethod
    def _nearest_city(latitude: float, longitude: float) -> tuple[str, float]:
        def distance(item: tuple[str, tuple[float, float]]) -> float:
            _, (lat, lon) = item
            lat1, lon1, lat2, lon2 = map(
                math.radians,
                (latitude, longitude, lat, lon),
            )
            dlat, dlon = lat2 - lat1, lon2 - lon1
            value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            return 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

        name, (lat, lon) = min(MAJOR_CITY_COORDS.items(), key=distance)
        return name, distance((name, (lat, lon)))
