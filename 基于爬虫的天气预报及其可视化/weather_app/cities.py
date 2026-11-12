"""城市检索、纠错与定位结果映射。"""

from __future__ import annotations

import difflib
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import CityNotFoundError


@dataclass(frozen=True, slots=True)
class City:
    name: str
    code: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class CityResolver:
    """读取城市码表，并提供联想、别名和轻微错字容错。"""

    # 常见城市的拼音别名，方便输入英文或拼音时联想。
    PINYIN_ALIASES = {
        "beijing": "北京",
        "shanghai": "上海",
        "guangzhou": "广州",
        "shenzhen": "深圳",
        "chengdu": "成都",
        "chongqing": "重庆",
        "hangzhou": "杭州",
        "nanjing": "南京",
        "wuhan": "武汉",
        "xian": "西安",
        "xiann": "西安",
        "suzhou": "苏州",
        "tianjin": "天津",
        "qingdao": "青岛",
        "changsha": "长沙",
        "zhengzhou": "郑州",
        "kunming": "昆明",
        "dalian": "大连",
        "xiamen": "厦门",
        "fuzhou": "福州",
        "jinan": "济南",
        "shenyang": "沈阳",
        "changchun": "长春",
        "harbin": "哈尔滨",
        "hefei": "合肥",
        "nanchang": "南昌",
        "guiyang": "贵阳",
        "nanning": "南宁",
        "haikou": "海口",
        "sanya": "三亚",
        "lanzhou": "兰州",
        "xining": "西宁",
        "yinchuan": "银川",
        "urumqi": "乌鲁木齐",
        "lhasa": "拉萨",
        "hohhot": "呼和浩特",
        "taiyuan": "太原",
        "shijiazhuang": "石家庄",
        "shenzhenshi": "深圳",
        "香港": "香港",
        "xianggang": "香港",
        "macao": "澳门",
        "aomen": "澳门",
        "taipei": "台北市",
    }

    COMMON_TYPOS = {
        "北就": "北京",
        "上晦": "上海",
        "广洲": "广州",
        "深川": "深圳",
        "成嘟": "成都",
        "重亲": "重庆",
        "杭洲": "杭州",
        "南就": "南京",
        "武汗": "武汉",
        "西按": "西安",
        "苏洲": "苏州",
    }

    SUFFIXES = ("特别行政区", "自治区", "自治州", "地区", "新区", "县城", "市", "县", "区")

    def __init__(self, city_file: Path | str) -> None:
        self._city_file = Path(city_file)
        self._cities: dict[str, City] = {}
        self._normalized_index: dict[str, str] = {}
        self._load_lock = threading.Lock()
        self._loaded = False
        self._load()

    def _load(self) -> None:
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            if not self._city_file.exists():
                raise RuntimeError(f"城市码表不存在：{self._city_file}")
            for raw_line in self._city_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                match = re.match(r"^(.+?)=(\d{9,12})$", line)
                if not match:
                    continue
                name, code = match.groups()
                self._cities.setdefault(name, City(name=name, code=code))
            for name in self._cities:
                normalized = self._normalize(name)
                self._normalized_index.setdefault(normalized, name)
            self._loaded = True

    @staticmethod
    def _normalize(value: str) -> str:
        text = re.sub(r"\s+", "", value or "").lower()
        return re.sub(r"[，。,.!！?？、]", "", text)

    def _strip_suffix(self, query: str) -> str:
        for suffix in self.SUFFIXES:
            if query.endswith(suffix) and len(query) > len(suffix):
                return query[: -len(suffix)]
        return query

    def _direct_name(self, query: str) -> str | None:
        normalized = self._normalize(query)
        if not normalized:
            return None
        if normalized in self._normalized_index:
            return self._normalized_index[normalized]
        typo_target = self.COMMON_TYPOS.get(normalized)
        if typo_target and typo_target in self._cities:
            return typo_target
        alias_target = self.PINYIN_ALIASES.get(normalized)
        if alias_target and alias_target in self._cities:
            return alias_target
        stripped = self._strip_suffix(normalized)
        if stripped in self._normalized_index:
            return self._normalized_index[stripped]
        return None

    def suggestions(self, query: str, limit: int = 8) -> list[dict]:
        """返回带相关度的城市建议，完全无结果时返回热门城市。"""

        normalized = self._normalize(query)
        if not normalized:
            return [self._city_item(name, 1.0) for name in self._popular_names()[:limit]]

        scored: dict[str, float] = {}
        direct = self._direct_name(normalized)
        if direct:
            scored[direct] = 1.0

        stripped = self._strip_suffix(normalized)
        for name in self._cities:
            candidate = self._normalize(name)
            score = 0.0
            if candidate == normalized:
                score = 1.0
            elif candidate == stripped:
                score = 0.98
            elif candidate.startswith(stripped) or candidate.startswith(normalized):
                score = 0.86
            elif normalized in candidate or stripped in candidate:
                score = 0.76
            elif candidate[:1] == normalized[:1]:
                score = 0.5 + difflib.SequenceMatcher(None, normalized, candidate).ratio() * 0.2
            else:
                ratio = difflib.SequenceMatcher(None, stripped, candidate).ratio()
                if ratio >= 0.42:
                    score = ratio * 0.72
            if score > 0:
                scored[name] = max(scored.get(name, 0), score)

        for alias, target in self.PINYIN_ALIASES.items():
            if alias.startswith(normalized) or normalized.startswith(alias):
                scored[target] = max(scored.get(target, 0), 0.9)

        if not scored:
            # 极短或完全无关的输入使用字符重合度再兜底一次。
            for name in self._cities:
                common_chars = set(stripped) & set(name)
                if common_chars:
                    scored[name] = len(common_chars) / max(len(set(stripped) | set(name)), 1)

        ranked = sorted(
            scored.items(),
            key=lambda item: (-item[1], len(item[0]), item[0]),
        )[:limit]
        if not ranked:
            return [self._city_item(name, 0.1) for name in self._popular_names()[:limit]]
        return [self._city_item(name, round(score, 4)) for name, score in ranked]

    def _city_item(self, name: str, score: float) -> dict:
        city = self._cities[name]
        return {
            **city.to_dict(),
            "label": name,
            "score": score,
            "matched": "fuzzy" if score < 0.95 else "exact",
        }

    @staticmethod
    def _popular_names() -> list[str]:
        return [
            "北京",
            "上海",
            "广州",
            "深圳",
            "成都",
            "杭州",
            "重庆",
            "西安",
            "南京",
            "武汉",
        ]

    def resolve(self, query: str) -> City:
        direct_name = self._direct_name(query)
        if direct_name:
            return self._cities[direct_name]
        suggestions = self.suggestions(query, limit=5)
        if suggestions and suggestions[0]["score"] >= 0.68:
            return City(suggestions[0]["name"], suggestions[0]["code"])
        raise CityNotFoundError(
            f'没有找到“{query}”，请检查城市名称',
            suggestions=suggestions,
        )

    def resolve_any(self, candidates: list[str]) -> City | None:
        """按定位接口返回的行政区顺序依次尝试匹配。"""

        for candidate in candidates:
            if not candidate:
                continue
            direct = self._direct_name(candidate)
            if direct:
                return self._cities[direct]
        for candidate in candidates:
            if not candidate:
                continue
            suggestions = self.suggestions(candidate, limit=1)
            if suggestions and suggestions[0]["score"] >= 0.7:
                return City(suggestions[0]["name"], suggestions[0]["code"])
        return None

    @property
    def city_count(self) -> int:
        return len(self._cities)
