from datetime import date

import pytest

from landfinder import parse


@pytest.mark.parametrize(
    "text, expected",
    [
        ("15억 7,500", 157500),
        ("15억", 150000),
        ("9,800", 9800),
        ("1억 500", 10500),
        ("7,500만", 7500),
        (157500, 157500),
        ("", None),
        ("협의", None),
        (None, None),
    ],
)
def test_parse_price(text, expected):
    assert parse.parse_price(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10/25", (10, None, 25)),
        ("저/25", (None, "저", 25)),
        ("고/30", (None, "고", 30)),
        ("B1/10", (-1, None, 10)),
        ("", (None, None, None)),
    ],
)
def test_parse_floor(text, expected):
    assert parse.parse_floor(text) == expected


def test_parse_date():
    assert parse.parse_date("19940512") == date(1994, 5, 12)
    assert parse.parse_date("201003") == date(2010, 3, 1)
    assert parse.parse_date("2026.10.15") == date(2026, 10, 15)
    assert parse.parse_date("bad") is None


def test_complexes_keeps_apartments_only(load):
    items = parse.complexes(load("complexes.json"))
    assert [c.complex_no for c in items] == ["1001", "1003"]
    first = items[0]
    assert first.households == 1156
    assert first.build_year == 1994
    assert first.deal_count == 14
    assert first.address.endswith("수내동")


def test_pyeongs(load):
    items = parse.pyeongs(load("detail.json"))
    assert [(p.area_no, p.exclusive_area) for p in items] == [("1", 59.88), ("2", 84.97), ("3", 84.91)]


def test_listings(load):
    items = parse.listings(load("articles_p1.json"), "1001")
    first, low, small = items
    assert first.price == 157500
    assert first.exclusive_area == 84.97
    assert first.floor == 10 and first.top_floor == 25
    assert first.confirmed == date(2026, 10, 15)
    assert first.same_address_count == 3
    assert low.floor is None and low.floor_level == "저"
    assert small.price == 112000


def test_real_trades_skip_cancelled_and_sort(load):
    trades = parse.real_trades(load("real.json"), "2", 84.97)
    assert [(t.deal_date, t.price) for t in trades] == [
        (date(2026, 9, 2), 150000),
        (date(2026, 5, 11), 145000),
        (date(2024, 3, 15), 120000),
    ]
    assert all(t.exclusive_area == 84.97 and t.area_no == "2" for t in trades)
