from datetime import date, timedelta

import pytest

from landfinder.demo import DemoSource
from landfinder.models import Complex, Listing, Pyeong, RealTrade
from landfinder.naver import NaverError
from landfinder.search import Criteria, complex_listings, listing_passes, search, summarize_real

TODAY = date(2026, 10, 18)


def listing(no, price, area=84.97, floor=10, level=None, direction="남향", confirmed_days=1):
    return Listing(
        article_no=no, complex_no="C1", price=price, price_text="", exclusive_area=area, supply_area=None,
        area_name="", floor_text="", floor=floor, floor_level=level, top_floor=25, building="101동",
        direction=direction, confirmed=TODAY - timedelta(days=confirmed_days), description="",
    )


class FakeSource:
    name = "fake"

    def __init__(self, complexes, listings, trades, fail_on=None):
        self._complexes = complexes
        self._listings = listings
        self._trades = trades
        self.fail_on = fail_on
        self.real_calls = []

    def complexes(self, cortar_no):
        return self._complexes

    def listings(self, complex_no, max_pages=5):
        if complex_no == self.fail_on:
            raise NaverError("요청 제한")
        return self._listings.get(complex_no, [])

    def pyeongs(self, complex_no):
        return [Pyeong("1", "79", 59.88, 79.3), Pyeong("2", "112", 84.97, 112.4), Pyeong("3", "112B", 84.91, 112.9)]

    def real_trades(self, complex_no, pyeong, years=3):
        self.real_calls.append((complex_no, pyeong.area_no))
        return [t for t in self._trades.get(complex_no, []) if round(t.exclusive_area) == round(pyeong.exclusive_area)]


def cx(no, households=1000, year=2000, deals=5):
    return Complex(no, f"단지{no}", "수내동", households, 10, date(year, 1, 1), deals)


def trade(days_ago, price, area=84.97):
    return RealTrade(TODAY - timedelta(days=days_ago), price, 5, area)


def test_listing_filters():
    crit = Criteria(price_min=100000, price_max=150000, area_min=84, area_max=85, exclude_low_floor=True, south_only=True, confirmed_within_days=14)
    assert listing_passes(listing("a", 140000), crit, TODAY)
    assert not listing_passes(listing("b", 160000), crit, TODAY)  # 비쌈
    assert not listing_passes(listing("c", 140000, area=59.88), crit, TODAY)  # 면적
    assert not listing_passes(listing("d", 140000, floor=2), crit, TODAY)  # 저층
    assert not listing_passes(listing("e", 140000, floor=None, level="저"), crit, TODAY)
    assert listing_passes(listing("f", 140000, floor=None, level="중"), crit, TODAY)
    assert not listing_passes(listing("g", 140000, direction="북향"), crit, TODAY)
    assert not listing_passes(listing("h", 140000, confirmed_days=30), crit, TODAY)
    assert not listing_passes(listing("i", None), crit, TODAY)  # 가격 모름


def test_area_boundary_tolerance():
    assert listing_passes(listing("a", 1, area=84.97), Criteria(area_max=84), TODAY) is False
    assert listing_passes(listing("a", 1, area=84.4), Criteria(area_max=84), TODAY) is True


def test_summarize_real_uses_window_median():
    s = summarize_real([trade(10, 150000), trade(100, 140000), trade(200, 130000), trade(500, 100000)], 85, 12, TODAY)
    assert s.median == 140000
    assert s.count == 3
    assert s.latest.price == 150000


def test_search_ranks_and_computes_gap():
    source = FakeSource(
        [cx("C1"), cx("C2", households=300), cx("C3", year=1985), cx("C4", deals=0)],
        {
            "C1": [listing("1", 145000), listing("2", 160000), listing("3", 110000, area=59.88)],
            "C2": [listing("4", 150000)],
        },
        {"C1": [trade(30, 150000), trade(60, 150000)], "C2": []},
    )
    crit = Criteria(cortar_nos=["x"], area_min=80, area_max=90, households_min=200, build_year_min=1990)
    out = search(source, crit, today=TODAY)
    assert [r["complex"]["complex_no"] for r in out.results] == ["C1", "C2"]
    c1 = out.results[0]
    assert c1["matched_count"] == 2
    assert c1["min_price"] == 145000
    assert c1["min_gap"] == pytest.approx(145000 / 150000 - 1)
    assert c1["real"][0]["bucket"] == 85 and c1["real"][0]["median"] == 150000
    # 85㎡ 두 타입(2, 3)의 실거래를 모두 조회하고 59㎡는 조회하지 않는다.
    assert sorted(a for c, a in source.real_calls if c == "C1") == ["2", "3"]
    assert out.results[1]["min_gap"] is None  # 실거래 없음


def test_max_gap_filter_drops_expensive_and_unknown():
    source = FakeSource(
        [cx("C1"), cx("C2")],
        {"C1": [listing("1", 145000), listing("2", 170000)], "C2": [listing("3", 150000)]},
        {"C1": [trade(30, 150000)]},
    )
    out = search(source, Criteria(cortar_nos=["x"], max_gap=0.0), today=TODAY)
    assert [r["complex"]["complex_no"] for r in out.results] == ["C1"]
    assert out.results[0]["matched_count"] == 1


def test_max_complexes_warns_and_keeps_biggest():
    source = FakeSource([cx(f"C{i}", households=100 * i) for i in range(1, 6)], {}, {})
    out = search(source, Criteria(cortar_nos=["x"], max_complexes=2), today=TODAY)
    assert out.checked == 2
    assert "세대수가 많은 2곳" in out.warnings[0]


def test_naver_error_keeps_partial_results():
    source = FakeSource([cx("C1", households=900), cx("C2", households=100)], {"C1": [listing("1", 1)]}, {}, fail_on="C2")
    out = search(source, Criteria(cortar_nos=["x"]), today=TODAY)
    assert [r["complex"]["complex_no"] for r in out.results] == ["C1"]
    assert "멈췄습니다" in out.warnings[-1]


def test_cancel():
    source = FakeSource([cx("C1"), cx("C2")], {"C1": [listing("1", 1)], "C2": [listing("2", 1)]}, {})
    calls = []
    out = search(source, Criteria(cortar_nos=["x"]), cancelled=lambda: len(calls) > 0, progress=lambda *a: calls.append(a), today=TODAY)
    assert out.results == []
    assert "취소" in out.warnings[0]


def test_complex_listings_all_vs_filtered():
    source = FakeSource([], {"C1": [listing("1", 160000), listing("2", 140000), listing("3", 100000, area=59.88)]}, {"C1": [trade(10, 150000)]})
    crit = Criteria(area_min=80)
    filtered = complex_listings(source, "C1", crit, today=TODAY)
    assert [r["article_no"] for r in filtered["listings"]] == ["2", "1"]  # 가격 오름차순
    assert filtered["total_listings"] == 3
    everything = complex_listings(source, "C1", crit, apply_filter=False, today=TODAY)
    assert len(everything["listings"]) == 3


def test_demo_source_end_to_end():
    demo = DemoSource()
    dongs = [r.cortar_no for r in demo.regions("4113500000")]
    out = search(demo, Criteria(cortar_nos=dongs, area_min=59, area_max=86))
    assert out.results
    for r in out.results:
        assert r["complex"]["name"].startswith("데모")
        assert r["matched_count"] > 0
