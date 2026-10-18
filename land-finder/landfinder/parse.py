"""네이버 부동산 응답(JSON)을 모델로 바꾸는 함수들.

네이버 부동산은 공식 API가 없고 웹사이트가 쓰는 내부 API를 사용한다.
필드가 바뀌어도 앱 전체가 죽지 않도록 모든 필드를 관대하게 읽는다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import Complex, Listing, Pyeong, RealTrade, Region

_PRICE_RE = re.compile(r"^\s*(?:(\d+)\s*억)?\s*([\d,]+)?\s*(?:만)?\s*$")


def parse_price(value: Any) -> Optional[int]:
    """'15억 7,500' -> 157500, '9억' -> 90000, '7,500' -> 7500 (만원)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    m = _PRICE_RE.match(text)
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    eok = int(m.group(1)) if m.group(1) else 0
    rest = int(m.group(2).replace(",", "")) if m.group(2) else 0
    return eok * 10_000 + rest


def parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def parse_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def parse_date(value: Any) -> Optional[date]:
    """'20261010', '2026.10.10', '2026-10-10', '199301'(일 없음) 지원."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    try:
        if len(digits) >= 8:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]) or 1)
        if len(digits) == 6:
            return date(int(digits[:4]), int(digits[4:6]) or 1, 1)
        if len(digits) == 4:
            return date(int(digits), 1, 1)
    except ValueError:
        return None
    return None


def parse_floor(text: Any) -> Tuple[Optional[int], Optional[str], Optional[int]]:
    """'10/15' -> (10, None, 15), '저/20' -> (None, '저', 20), 'B1/10' -> (-1, None, 10)."""
    if not text:
        return None, None, None
    parts = str(text).split("/")
    this = parts[0].strip()
    top = parse_int(parts[1]) if len(parts) > 1 else None
    if this in ("저", "중", "고"):
        return None, this, top
    if this.upper().startswith("B"):
        n = parse_int(this[1:])
        return (-n if n else None), None, top
    return parse_int(this), None, top


def regions(data: Dict[str, Any]) -> List[Region]:
    return [
        Region(cortar_no=str(r.get("cortarNo", "")), name=r.get("cortarName", ""), type=r.get("cortarType", ""))
        for r in data.get("regionList") or []
        if r.get("cortarNo")
    ]


def complexes(data: Dict[str, Any]) -> List[Complex]:
    result = []
    for c in data.get("complexList") or []:
        if c.get("realEstateTypeCode") not in (None, "APT"):
            continue  # 아파트만
        result.append(
            Complex(
                complex_no=str(c.get("complexNo", "")),
                name=c.get("complexName", ""),
                address=c.get("cortarAddress") or c.get("detailAddress") or "",
                households=parse_int(c.get("totalHouseholdCount")),
                buildings=parse_int(c.get("totalBuildingCount")),
                approve_date=parse_date(c.get("useApproveYmd")),
                deal_count=parse_int(c.get("dealCount")),
                high_floor=parse_int(c.get("highFloor")),
                latitude=parse_float(c.get("latitude")),
                longitude=parse_float(c.get("longitude")),
            )
        )
    return [c for c in result if c.complex_no]


def pyeongs(data: Dict[str, Any]) -> List[Pyeong]:
    items = data.get("complexPyeongDetailList") or data.get("pyeongList") or []
    return [
        Pyeong(
            area_no=str(p.get("pyeongNo", "")),
            name=p.get("pyeongName") or p.get("pyeongName2") or "",
            exclusive_area=parse_float(p.get("exclusiveArea")),
            supply_area=parse_float(p.get("supplyArea")),
            households=parse_int(p.get("householdCountByPyeong")),
        )
        for p in items
        if p.get("pyeongNo") is not None
    ]


def listings(data: Dict[str, Any], complex_no: str) -> List[Listing]:
    result = []
    for a in data.get("articleList") or []:
        floor, level, top = parse_floor(a.get("floorInfo"))
        price_text = a.get("dealOrWarrantPrc") or ""
        result.append(
            Listing(
                article_no=str(a.get("articleNo", "")),
                complex_no=complex_no,
                price=parse_price(price_text),
                price_text=price_text,
                exclusive_area=parse_float(a.get("area2")),
                supply_area=parse_float(a.get("area1")),
                area_name=str(a.get("areaName") or ""),
                floor_text=a.get("floorInfo") or "",
                floor=floor,
                floor_level=level,
                top_floor=top,
                building=a.get("buildingName") or "",
                direction=a.get("direction") or "",
                confirmed=parse_date(a.get("articleConfirmYmd")),
                description=a.get("articleFeatureDesc") or "",
                tags=list(a.get("tagList") or []),
                realtor=a.get("realtorName") or "",
                same_address_count=parse_int(a.get("sameAddrCnt")) or 1,
            )
        )
    return [x for x in result if x.article_no]


def _iter_real_items(data: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for month in data.get("realPriceOnMonthList") or []:
        for item in month.get("realPriceList") or []:
            yield item
    # 다른 형태(평면 목록)로 올 때
    for item in data.get("realPriceList") or []:
        yield item


def real_trades(data: Dict[str, Any], area_no: Optional[str], default_area: Optional[float]) -> List[RealTrade]:
    result = []
    for item in _iter_real_items(data):
        if str(item.get("deleteYn", "")).lower() in ("true", "y") or item.get("deleteYn") is True:
            continue  # 계약 해제
        price = parse_int(item.get("dealPrice")) or parse_price(item.get("formattedPrice"))
        year = parse_int(item.get("tradeYear"))
        month = parse_int(item.get("tradeMonth"))
        day = parse_int(item.get("tradeDate")) or 1
        if not (price and year and month):
            continue
        try:
            deal_date = date(year, month, day)
        except ValueError:
            continue
        result.append(
            RealTrade(
                deal_date=deal_date,
                price=price,
                floor=parse_int(item.get("floor")),
                exclusive_area=parse_float(item.get("exclusiveArea")) or default_area,
                area_no=area_no,
            )
        )
    result.sort(key=lambda t: t.deal_date, reverse=True)
    return result
