"""네이버에 접속하지 않고 화면을 확인하기 위한 가짜 데이터.

단지명은 실제 단지와 헷갈리지 않도록 모두 '데모'로 시작한다.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Dict, List

from .models import Complex, Listing, Pyeong, RealTrade, Region

_TREE: Dict[str, List[Region]] = {
    "0000000000": [Region("4100000000", "경기도", "city"), Region("1100000000", "서울시", "city")],
    "4100000000": [Region("4113500000", "성남시 분당구", "dvsn"), Region("4111700000", "수원시 영통구", "dvsn")],
    "1100000000": [Region("1168000000", "강남구", "dvsn")],
    "4113500000": [
        Region("4113510900", "수내동", "sec"),
        Region("4113511000", "정자동", "sec"),
        Region("4113510500", "서현동", "sec"),
        Region("4113510600", "이매동", "sec"),
    ],
    "4111700000": [Region("4111710300", "매탄동", "sec")],
    "1168000000": [Region("1168010300", "개포동", "sec")],
}

_DIRECTIONS = ["남향", "남동향", "남서향", "동향", "서향", "북향"]
_DESCS = ["올수리, 즉시입주", "로열동 로열층", "세안고 매물", "역세권 초품아", "확장형, 채광 좋음", "급매"]
_TODAY = date.today()


class DemoSource:
    name = "demo"

    def __init__(self) -> None:
        self._complexes: Dict[str, Complex] = {}
        self._pyeongs: Dict[str, List[Pyeong]] = {}
        self._listings: Dict[str, List[Listing]] = {}
        self._trades: Dict[str, Dict[str, List[RealTrade]]] = {}
        self._by_region: Dict[str, List[str]] = {}
        for region_list in _TREE.values():
            for region in region_list:
                if region.type == "sec":
                    self._build_region(region)

    def _build_region(self, region: Region) -> None:
        rng = random.Random(region.cortar_no)
        ids = []
        for i in range(rng.randint(5, 9)):
            no = f"9{region.cortar_no[-4:]}{i:02d}"
            ids.append(no)
            year = rng.randint(1992, 2020)
            households = rng.choice([180, 320, 540, 820, 1150, 1800, 2400])
            self._complexes[no] = Complex(
                complex_no=no,
                name=f"데모 {region.name[:-1]}{chr(ord('A') + i)}단지",
                address=f"데모시 {region.name}",
                households=households,
                buildings=max(2, households // 120),
                approve_date=date(year, rng.randint(1, 12), 1),
                deal_count=rng.randint(0, 40),
                high_floor=rng.choice([15, 20, 25, 30]),
            )
            unit = rng.uniform(1300, 2400) * (1 + (year - 1992) / 60)  # ㎡당 만원
            areas = sorted(rng.sample([39.9, 59.9, 74.5, 84.9, 101.9, 134.5], k=rng.randint(2, 4)))
            self._pyeongs[no] = [
                Pyeong(str(j + 1), f"{int(a * 1.3)}{'AB'[j % 2]}", a, round(a * 1.32, 2)) for j, a in enumerate(areas)
            ]
            self._trades[no] = {}
            for p in self._pyeongs[no]:
                trades = []
                base = unit * p.exclusive_area
                for _ in range(rng.randint(0, 14)):
                    days_ago = rng.randint(5, 3 * 365)
                    trend = 1 - days_ago / 365 * rng.uniform(0.02, 0.10)
                    trades.append(
                        RealTrade(
                            deal_date=_TODAY - timedelta(days=days_ago),
                            price=int(round(base * trend * rng.uniform(0.95, 1.05), -2)),
                            floor=rng.randint(1, self._complexes[no].high_floor or 15),
                            exclusive_area=p.exclusive_area,
                            area_no=p.area_no,
                        )
                    )
                trades.sort(key=lambda t: t.deal_date, reverse=True)
                self._trades[no][p.area_no] = trades
            listings = []
            for k in range(self._complexes[no].deal_count or 0):
                p = rng.choice(self._pyeongs[no])
                top = self._complexes[no].high_floor or 15
                floor = rng.randint(1, top)
                price = int(round(unit * p.exclusive_area * rng.uniform(0.97, 1.18), -2))
                listings.append(
                    Listing(
                        article_no=f"{no}{k:03d}",
                        complex_no=no,
                        price=price,
                        price_text=_format(price),
                        exclusive_area=p.exclusive_area,
                        supply_area=p.supply_area,
                        area_name=p.name,
                        floor_text=f"{floor}/{top}" if rng.random() > 0.3 else f"{'저중고'[min(2, floor * 3 // (top + 1))]}/{top}",
                        floor=floor,
                        floor_level=None,
                        top_floor=top,
                        building=f"{rng.randint(101, 112)}동",
                        direction=rng.choice(_DIRECTIONS),
                        confirmed=_TODAY - timedelta(days=rng.randint(0, 40)),
                        description=rng.choice(_DESCS),
                        realtor=f"데모공인중개사 {rng.randint(1, 9)}",
                        same_address_count=rng.randint(1, 3),
                    )
                )
            # 층 표기가 '저/중/고'인 매물은 실제 네이버처럼 숫자 층을 모르는 것으로 둔다.
            for item in listings:
                if not item.floor_text.split("/")[0].isdigit():
                    item.floor_level = item.floor_text.split("/")[0]
                    item.floor = None
            listings.sort(key=lambda x: x.price or 0)
            self._listings[no] = listings
        self._by_region[region.cortar_no] = ids

    def regions(self, cortar_no: str = "0000000000") -> List[Region]:
        return list(_TREE.get(cortar_no, []))

    def complexes(self, cortar_no: str) -> List[Complex]:
        return [self._complexes[no] for no in self._by_region.get(cortar_no, [])]

    def pyeongs(self, complex_no: str) -> List[Pyeong]:
        return list(self._pyeongs.get(complex_no, []))

    def listings(self, complex_no: str, max_pages: int = 5) -> List[Listing]:
        return list(self._listings.get(complex_no, []))

    def real_trades(self, complex_no: str, pyeong: Pyeong, years: int = 3) -> List[RealTrade]:
        cutoff = _TODAY - timedelta(days=365 * years)
        return [t for t in self._trades.get(complex_no, {}).get(pyeong.area_no, []) if t.deal_date >= cutoff]


def _format(price: int) -> str:
    eok, rest = divmod(price, 10_000)
    if eok == 0:
        return f"{rest:,}"
    return f"{eok}억" if rest == 0 else f"{eok}억 {rest:,}"
