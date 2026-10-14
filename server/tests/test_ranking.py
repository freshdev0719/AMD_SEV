from datetime import date, timedelta

import pytest

from app.ranking import Metric, TradeRow, compute_stats, find_new_highs, percentile_ranks, rank

AS_OF = date(2026, 10, 14)
_next_id = iter(range(1, 10_000))


def trade(cid, days_ago, price, area=84.9, deal_type="중개거래", cancelled=False):
    return TradeRow(next(_next_id), cid, AS_OF - timedelta(days=days_ago), area, 5, price, deal_type, cancelled)


def test_growth_compares_same_area_only():
    trades = [
        # 84㎡: 10억 -> 12억 (+20%)
        trade("A", 400, 100_000),
        trade("A", 410, 100_000),
        trade("A", 10, 120_000),
        trade("A", 20, 120_000),
        # 최근에 대형 평형만 팔려도 상승률이 부풀려지면 안 된다 (비교 대상 없음)
        trade("A", 5, 300_000, area=134.5),
    ]
    s = compute_stats(trades, AS_OF)["A"]
    assert s.volume == 3
    assert s.prior_volume == 2
    assert s.growth == pytest.approx(0.20)


def test_cancelled_and_direct_deals_excluded():
    trades = [
        trade("A", 400, 100_000),
        trade("A", 401, 100_000),
        trade("A", 10, 100_000),
        trade("A", 11, 100_000),
        trade("A", 12, 200_000, cancelled=True),
        trade("A", 13, 50_000, deal_type="직거래"),
    ]
    s = compute_stats(trades, AS_OF)["A"]
    assert s.volume == 2
    assert s.growth == pytest.approx(0.0)

    s_all = compute_stats(trades, AS_OF, exclude_direct=False)["A"]
    assert s_all.volume == 3


def test_growth_requires_min_samples():
    trades = [trade("A", 400, 100_000), trade("A", 10, 150_000)]
    assert compute_stats(trades, AS_OF)["A"].growth is None
    assert compute_stats(trades, AS_OF, min_samples=1)["A"].growth == pytest.approx(0.5)


def test_new_highs_ignore_same_day_and_first_trade():
    trades = [
        trade("A", 100, 100_000),
        trade("A", 50, 110_000),  # 신고가
        trade("A", 50, 120_000),  # 같은 날 거래끼리는 비교하지 않음 -> 직전 최고가 10억
        trade("A", 10, 115_000),  # 12억보다 낮음
        trade("B", 10, 999_999),  # 첫 거래는 신고가 아님
    ]
    highs = find_new_highs(trades)
    assert sorted(highs.values()) == [100_000, 100_000]
    assert len(highs) == 2


def test_percentile_ranks_ties():
    assert percentile_ranks([1.0, 2.0, 2.0, 3.0]) == [0.0, pytest.approx(0.5), pytest.approx(0.5), 1.0]
    assert percentile_ranks([5.0]) == [1.0]


def test_rank_orders_by_metric():
    trades = []
    # A: 거래 최다·상승률 최저, B: 거래 최소·상승률 최고, C: 둘 다 낮은 편, D: 둘 다 높은 편
    for d in range(5):
        trades += [trade("A", 400 + d, 100_000), trade("A", 10 + d, 101_000)]
    for d in range(2):
        trades += [trade("B", 400 + d, 100_000), trade("B", 10 + d, 150_000)]
    for d in range(3):
        trades += [trade("C", 400 + d, 100_000), trade("C", 10 + d, 120_000)]
    for d in range(4):
        trades += [trade("D", 400 + d, 100_000), trade("D", 10 + d, 130_000)]

    stats = compute_stats(trades, AS_OF)
    assert [s.complex_id for s in rank(stats, Metric.volume)] == ["A", "D", "C", "B"]
    assert [s.complex_id for s in rank(stats, Metric.growth)] == ["B", "D", "C", "A"]
    # A와 B는 점수 0.5로 같고, 동점이면 거래량이 많은 쪽이 앞선다.
    assert [s.complex_id for s in rank(stats, Metric.composite)] == ["D", "A", "B", "C"]
    assert stats["D"].score == pytest.approx(2 / 3)
