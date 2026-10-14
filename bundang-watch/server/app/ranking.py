"""단지별 거래량·가격 상승률 집계와 순위 계산.

- 거래량: 최근 window_days일 동안의 유효 거래 건수
- 거래량 증가율: 같은 기간 1년 전 대비 거래 건수 변화
- 가격 상승률: 같은 단지·같은 전용면적(㎡ 반올림) 끼리 최근 기간 중위가격을
  1년 전 같은 기간 중위가격과 비교하고, 면적별 결과를 표본 수로 가중 평균
- 종합 점수: 거래량과 가격 상승률의 백분위 순위를 가중 평균
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from statistics import median

DIRECT_DEAL = "직거래"


class Metric(str, Enum):
    composite = "composite"
    volume = "volume"
    growth = "growth"
    volume_change = "volume_change"


@dataclass(frozen=True)
class TradeRow:
    id: int
    complex_id: str
    deal_date: date
    area: float
    floor: int | None
    price: int
    deal_type: str | None
    cancelled: bool


@dataclass
class ComplexStats:
    complex_id: str
    volume: int = 0
    prior_volume: int = 0
    volume_change: float | None = None
    growth: float | None = None
    growth_samples: int = 0
    new_highs: int = 0
    latest: TradeRow | None = None
    score: float | None = None


def area_bucket(area: float) -> int:
    return int(round(area))


def is_valid(trade: TradeRow, exclude_direct: bool) -> bool:
    """해제된 계약과 (선택적으로) 시세와 동떨어지기 쉬운 직거래를 제외한다."""
    if trade.cancelled:
        return False
    return not (exclude_direct and trade.deal_type == DIRECT_DEAL)


def find_new_highs(trades: list[TradeRow]) -> dict[int, int]:
    """신고가 거래의 id -> 직전 최고가.

    같은 단지·같은 면적에서 그 날짜 이전의 모든 거래보다 비싸면 신고가로 본다.
    호출하는 쪽에서 유효 거래만 넘겨야 한다.
    """
    groups: dict[tuple[str, int], list[TradeRow]] = defaultdict(list)
    for t in trades:
        groups[(t.complex_id, area_bucket(t.area))].append(t)

    result: dict[int, int] = {}
    for rows in groups.values():
        rows.sort(key=lambda t: t.deal_date)
        prev_max: int | None = None
        i = 0
        while i < len(rows):
            day = rows[i].deal_date
            day_max = prev_max
            while i < len(rows) and rows[i].deal_date == day:
                t = rows[i]
                if prev_max is not None and t.price > prev_max:
                    result[t.id] = prev_max
                day_max = t.price if day_max is None else max(day_max, t.price)
                i += 1
            prev_max = day_max
    return result


def _growth(recent: dict[int, list[int]], prior: dict[int, list[int]]) -> tuple[float | None, int]:
    weighted_sum = 0.0
    weight = 0
    for bucket, recent_prices in recent.items():
        prior_prices = prior.get(bucket)
        if not prior_prices:
            continue
        w = min(len(recent_prices), len(prior_prices))
        weighted_sum += w * (median(recent_prices) / median(prior_prices) - 1)
        weight += w
    if weight == 0:
        return None, 0
    return weighted_sum / weight, weight


def percentile_ranks(values: list[float]) -> list[float]:
    """0(최저)~1(최고) 백분위. 동점은 평균 순위."""
    n = len(values)
    if n == 1:
        return [1.0]
    first: dict[float, int] = {}
    last: dict[float, int] = {}
    for i, v in enumerate(sorted(values)):
        first.setdefault(v, i)
        last[v] = i
    return [(first[v] + last[v]) / 2 / (n - 1) for v in values]


def compute_stats(
    trades: list[TradeRow],
    as_of: date,
    window_days: int = 90,
    exclude_direct: bool = True,
    min_samples: int = 2,
    volume_weight: float = 0.5,
) -> dict[str, ComplexStats]:
    recent_start = as_of - timedelta(days=window_days)
    prior_end = as_of - timedelta(days=365)
    prior_start = prior_end - timedelta(days=window_days)

    valid = [t for t in trades if is_valid(t, exclude_direct) and t.deal_date <= as_of]
    highs = find_new_highs(valid)

    stats: dict[str, ComplexStats] = {}
    recent_prices: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    prior_prices: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))

    for t in valid:
        s = stats.setdefault(t.complex_id, ComplexStats(t.complex_id))
        if s.latest is None or t.deal_date > s.latest.deal_date:
            s.latest = t
        if recent_start < t.deal_date <= as_of:
            s.volume += 1
            recent_prices[t.complex_id][area_bucket(t.area)].append(t.price)
            if t.id in highs:
                s.new_highs += 1
        elif prior_start < t.deal_date <= prior_end:
            s.prior_volume += 1
            prior_prices[t.complex_id][area_bucket(t.area)].append(t.price)

    for cid, s in stats.items():
        if s.prior_volume:
            s.volume_change = s.volume / s.prior_volume - 1
        growth, samples = _growth(recent_prices.get(cid, {}), prior_prices.get(cid, {}))
        s.growth_samples = samples
        if samples >= min_samples:
            s.growth = growth

    eligible = [s for s in stats.values() if s.growth is not None and s.volume > 0]
    if eligible:
        vol_pct = percentile_ranks([float(s.volume) for s in eligible])
        growth_pct = percentile_ranks([s.growth for s in eligible])  # type: ignore[misc]
        for s, v, g in zip(eligible, vol_pct, growth_pct):
            s.score = volume_weight * v + (1 - volume_weight) * g

    return stats


def rank(stats: dict[str, ComplexStats], metric: Metric, limit: int = 10) -> list[ComplexStats]:
    items = list(stats.values())
    if metric is Metric.volume:
        items = [s for s in items if s.volume > 0]
        items.sort(key=lambda s: (s.volume, s.growth if s.growth is not None else float("-inf")), reverse=True)
    elif metric is Metric.growth:
        items = [s for s in items if s.growth is not None]
        items.sort(key=lambda s: s.growth, reverse=True)  # type: ignore[arg-type,return-value]
    elif metric is Metric.volume_change:
        items = [s for s in items if s.volume_change is not None and s.volume > 0]
        items.sort(key=lambda s: (s.volume_change, s.volume), reverse=True)  # type: ignore[arg-type,return-value]
    else:
        items = [s for s in items if s.score is not None]
        items.sort(key=lambda s: (s.score, s.volume), reverse=True)  # type: ignore[arg-type,return-value]
    return items[:limit]
