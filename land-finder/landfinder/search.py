"""검색 조건, 매물 필터, 단지 검색 파이프라인.

데이터 소스(네이버 / 데모)는 아래 메서드만 있으면 된다:
regions(cortar_no), complexes(cortar_no), pyeongs(complex_no),
listings(complex_no), real_trades(complex_no, pyeong, years)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, fields
from datetime import date, timedelta
from statistics import median
from typing import Any, Callable, Dict, List, Optional

from .models import Complex, Listing, RealTrade, area_bucket, to_dict
from .naver import NaverError

SOUTH_DIRECTIONS = ("남향", "남동향", "남서향")


@dataclass
class Criteria:
    cortar_nos: List[str] = field(default_factory=list)  # 읍·면·동 코드
    price_min: Optional[int] = None  # 만원
    price_max: Optional[int] = None
    area_min: Optional[float] = None  # 전용 ㎡
    area_max: Optional[float] = None
    households_min: Optional[int] = None
    build_year_min: Optional[int] = None
    build_year_max: Optional[int] = None
    exclude_low_floor: bool = False
    low_floor_max: int = 2  # 이 층 이하와 '저'층은 저층으로 본다
    south_only: bool = False
    confirmed_within_days: Optional[int] = None
    max_gap: Optional[float] = None  # 0.05 = 같은 면적 실거래 중위가 대비 +5% 이하 호가만
    real_months: int = 12  # 실거래 비교 기간
    max_complexes: int = 60  # 한 번에 매물까지 확인할 최대 단지 수

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Criteria":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names and v is not None and v != ""})


@dataclass
class AreaReal:
    """한 전용면적 묶음의 실거래 요약."""

    bucket: int
    median: Optional[int]  # 비교 기간 중위가
    count: int  # 비교 기간 거래 수
    latest: Optional[RealTrade]
    recent: List[RealTrade]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "bucket": self.bucket,
            "median": self.median,
            "count": self.count,
            "latest": to_dict(self.latest) if self.latest else None,
            "recent": [to_dict(t) for t in self.recent],
        }


ProgressFn = Callable[[str, int, int], None]


def complex_passes(c: Complex, crit: Criteria) -> bool:
    if crit.households_min and (c.households or 0) < crit.households_min:
        return False
    year = c.build_year
    if crit.build_year_min and (year is None or year < crit.build_year_min):
        return False
    if crit.build_year_max and (year is None or year > crit.build_year_max):
        return False
    return c.deal_count != 0  # 매매 매물이 하나도 없는 단지는 건너뜀 (모르면 확인)


def is_low_floor(item: Listing, low_floor_max: int) -> bool:
    if item.floor_level == "저":
        return True
    return item.floor is not None and item.floor <= low_floor_max


def listing_passes(item: Listing, crit: Criteria, today: date) -> bool:
    if crit.price_min is not None or crit.price_max is not None:
        if item.price is None:
            return False
        if crit.price_min is not None and item.price < crit.price_min:
            return False
        if crit.price_max is not None and item.price > crit.price_max:
            return False
    if crit.area_min is not None or crit.area_max is not None:
        if item.exclusive_area is None:
            return False
        # 표기 반올림 차이로 경계값이 빠지지 않게 0.5㎡ 여유를 둔다.
        if crit.area_min is not None and item.exclusive_area < crit.area_min - 0.5:
            return False
        if crit.area_max is not None and item.exclusive_area > crit.area_max + 0.5:
            return False
    if crit.exclude_low_floor and is_low_floor(item, crit.low_floor_max):
        return False
    if crit.south_only and item.direction not in SOUTH_DIRECTIONS:
        return False
    if crit.confirmed_within_days is not None:
        if item.confirmed is None or (today - item.confirmed).days > crit.confirmed_within_days:
            return False
    return True


def summarize_real(trades: List[RealTrade], bucket: int, months: int, today: date) -> AreaReal:
    trades = sorted(trades, key=lambda t: t.deal_date, reverse=True)
    since = today - timedelta(days=round(months * 30.44))
    window = [t.price for t in trades if t.deal_date >= since]
    return AreaReal(
        bucket=bucket,
        median=int(median(window)) if window else None,
        count=len(window),
        latest=trades[0] if trades else None,
        recent=trades[:10],
    )


def real_by_bucket(source: Any, complex_no: str, buckets: List[int], crit: Criteria, today: date) -> Dict[int, AreaReal]:
    """필요한 면적 묶음의 실거래만 평형 타입별로 가져와 합친다."""
    by_bucket: Dict[int, List] = defaultdict(list)
    for p in source.pyeongs(complex_no):
        b = area_bucket(p.exclusive_area)
        if b is not None and b in buckets:
            by_bucket[b].append(p)

    years = max(3, math.ceil(crit.real_months / 12))
    result = {}
    for b in buckets:
        trades: List[RealTrade] = []
        for p in by_bucket.get(b, []):
            trades.extend(source.real_trades(complex_no, p, years))
        result[b] = summarize_real(trades, b, crit.real_months, today)
    return result


def gap(price: Optional[int], real: Optional[AreaReal]) -> Optional[float]:
    if price is None or real is None or not real.median:
        return None
    return price / real.median - 1


def listing_row(item: Listing, real: Optional[AreaReal]) -> Dict[str, Any]:
    row = to_dict(item)
    row["bucket"] = area_bucket(item.exclusive_area)
    row["real_median"] = real.median if real else None
    row["gap"] = gap(item.price, real)
    return row


def evaluate_complex(source: Any, c: Complex, crit: Criteria, today: date) -> Optional[Dict[str, Any]]:
    """조건에 맞는 매물이 있으면 단지 요약을, 없으면 None."""
    all_listings = source.listings(c.complex_no)
    matched = [x for x in all_listings if listing_passes(x, crit, today)]
    if not matched:
        return None

    buckets = sorted({b for b in (area_bucket(x.exclusive_area) for x in matched) if b is not None})
    reals = real_by_bucket(source, c.complex_no, buckets, crit, today)
    rows = [listing_row(x, reals.get(area_bucket(x.exclusive_area))) for x in matched]
    if crit.max_gap is not None:
        rows = [r for r in rows if r["gap"] is not None and r["gap"] <= crit.max_gap]
        if not rows:
            return None

    priced = [r for r in rows if r["price"] is not None]
    cheapest = min(priced, key=lambda r: r["price"]) if priced else None
    gaps = [r["gap"] for r in rows if r["gap"] is not None]
    used_buckets = sorted({r["bucket"] for r in rows if r["bucket"] is not None})
    return {
        "complex": to_dict(c),
        "matched_count": len(rows),
        "total_listings": len(all_listings),
        "min_price": cheapest["price"] if cheapest else None,
        "min_price_area": cheapest["exclusive_area"] if cheapest else None,
        "min_gap": min(gaps) if gaps else None,
        "real": [reals[b].as_dict() for b in used_buckets if b in reals],
    }


@dataclass
class SearchOutcome:
    results: List[Dict[str, Any]]
    warnings: List[str]
    checked: int


def search(
    source: Any,
    crit: Criteria,
    progress: ProgressFn = lambda msg, done, total: None,
    cancelled: Callable[[], bool] = lambda: False,
    today: Optional[date] = None,
) -> SearchOutcome:
    today = today or date.today()
    warnings: List[str] = []
    if not crit.cortar_nos:
        return SearchOutcome([], ["지역(동)을 하나 이상 선택하세요."], 0)

    candidates: List[Complex] = []
    seen = set()
    for i, cortar in enumerate(crit.cortar_nos):
        progress("단지 목록을 불러오는 중", i, len(crit.cortar_nos))
        if cancelled():
            return SearchOutcome([], ["검색을 취소했습니다."], 0)
        try:
            for c in source.complexes(cortar):
                if c.complex_no not in seen and complex_passes(c, crit):
                    seen.add(c.complex_no)
                    candidates.append(c)
        except NaverError as e:
            return SearchOutcome([], [str(e)], 0)

    candidates.sort(key=lambda c: c.households or 0, reverse=True)
    if len(candidates) > crit.max_complexes:
        warnings.append(
            f"조건에 맞는 단지가 {len(candidates)}곳이라 세대수가 많은 {crit.max_complexes}곳만 매물을 확인했습니다. "
            "지역을 좁히거나 세대수·준공연도 조건을 더하세요."
        )
        candidates = candidates[: crit.max_complexes]

    results = []
    checked = 0
    for i, c in enumerate(candidates):
        if cancelled():
            warnings.append("검색을 취소했습니다. 그때까지 찾은 결과만 보여줍니다.")
            break
        progress(f"{c.name} 매물 확인 중", i, len(candidates))
        try:
            row = evaluate_complex(source, c, crit, today)
        except NaverError as e:
            warnings.append(f"{c.name}에서 멈췄습니다: {e}")
            break
        checked += 1
        if row:
            results.append(row)
    progress("완료", len(candidates), len(candidates))

    results.sort(key=lambda r: (r["matched_count"], -(r["min_price"] or 0)), reverse=True)
    return SearchOutcome(results, warnings, checked)


def complex_listings(source: Any, complex_no: str, crit: Criteria, apply_filter: bool = True, today: Optional[date] = None) -> Dict[str, Any]:
    """단지를 골랐을 때 보여줄 매물 목록과 면적별 실거래."""
    today = today or date.today()
    items = source.listings(complex_no)
    total = len(items)
    if apply_filter:
        items = [x for x in items if listing_passes(x, crit, today)]
    buckets = sorted({b for b in (area_bucket(x.exclusive_area) for x in items) if b is not None})
    reals = real_by_bucket(source, complex_no, buckets, crit, today)
    rows = [listing_row(x, reals.get(area_bucket(x.exclusive_area))) for x in items]
    if apply_filter and crit.max_gap is not None:
        rows = [r for r in rows if r["gap"] is not None and r["gap"] <= crit.max_gap]
    rows.sort(key=lambda r: (r["price"] is None, r["price"] or 0))
    return {
        "complex_no": complex_no,
        "total_listings": total,
        "listings": rows,
        "real": [reals[b].as_dict() for b in buckets],
    }
