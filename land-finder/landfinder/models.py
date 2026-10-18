"""데이터 모델. 금액은 모두 만원 단위 정수, 면적은 ㎡."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

PYEONG = 3.3058


@dataclass
class Region:
    cortar_no: str
    name: str
    type: str  # city / dvsn / sec


@dataclass
class Complex:
    complex_no: str
    name: str
    address: str
    households: Optional[int]
    buildings: Optional[int]
    approve_date: Optional[date]  # 사용승인일
    deal_count: Optional[int]  # 매매 매물 수 (네이버 집계)
    high_floor: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def build_year(self) -> Optional[int]:
        return self.approve_date.year if self.approve_date else None


@dataclass
class Pyeong:
    """단지의 평형 타입."""

    area_no: str
    name: str
    exclusive_area: Optional[float]
    supply_area: Optional[float]
    households: Optional[int] = None


@dataclass
class Listing:
    """매매 매물(호가)."""

    article_no: str
    complex_no: str
    price: Optional[int]
    price_text: str
    exclusive_area: Optional[float]
    supply_area: Optional[float]
    area_name: str
    floor_text: str  # "10/15", "저/20"
    floor: Optional[int]  # 숫자로 알 수 있을 때만
    floor_level: Optional[str]  # 저 / 중 / 고
    top_floor: Optional[int]
    building: str
    direction: str
    confirmed: Optional[date]
    description: str
    tags: List[str] = field(default_factory=list)
    realtor: str = ""
    same_address_count: int = 1


@dataclass
class RealTrade:
    """실거래."""

    deal_date: date
    price: int
    floor: Optional[int]
    exclusive_area: Optional[float]
    area_no: Optional[str] = None


def area_bucket(area: Optional[float]) -> Optional[int]:
    """같은 평형으로 볼 전용면적 묶음(㎡ 반올림)."""
    return int(round(area)) if area is not None else None


def to_dict(obj: Any) -> Dict[str, Any]:
    """JSON 응답용. date는 ISO 문자열로 바꾼다."""
    def convert(value: Any) -> Any:
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    data = convert(asdict(obj))
    if isinstance(obj, Complex):
        data["build_year"] = obj.build_year
    return data
