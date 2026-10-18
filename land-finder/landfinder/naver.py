"""네이버 부동산(new.land.naver.com) 비공식 API 클라이언트.

- 공식 API가 아니므로 네이버가 사이트를 바꾸면 동작하지 않을 수 있다.
- 웹페이지에 들어 있는 토큰(Bearer)을 가져와 요청에 붙인다.
  자동으로 못 가져오면 설정에서 브라우저 개발자도구로 본 토큰·쿠키를 직접 넣을 수 있다.
- 개인 용도로, 요청 사이 간격을 두고, 결과를 캐시해서 요청 수를 최소화한다.
"""

from __future__ import annotations

import random
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from . import parse
from .cache import Cache
from .models import Complex, Listing, Pyeong, RealTrade, Region

BASE_URL = "https://new.land.naver.com"
TOKEN_RE = re.compile(r'"token"\s*:\s*"([A-Za-z0-9_\-.]+)"')
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

HOUR = 3600
TTL_REGIONS = 30 * 24 * HOUR
TTL_COMPLEXES = 24 * HOUR
TTL_DETAIL = 7 * 24 * HOUR
TTL_LISTINGS = HOUR // 2
TTL_REAL = 12 * HOUR

ARTICLES_PER_PAGE = 20


class NaverError(RuntimeError):
    pass


def complex_url(complex_no: str, article_no: Optional[str] = None) -> str:
    url = f"{BASE_URL}/complexes/{complex_no}"
    return f"{url}?articleNo={article_no}" if article_no else url


class NaverLandClient:
    name = "naver"

    def __init__(
        self,
        cache: Cache,
        token: str = "",
        cookie: str = "",
        min_interval: float = 1.0,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.cache = cache
        self._manual_token = token.strip()
        self._token: Optional[str] = self._manual_token or None
        self.min_interval = min_interval
        self._sleep = sleep
        self._last_request = 0.0
        self._lock = threading.Lock()  # 검색 작업과 화면 요청이 동시에 와도 한 번에 하나씩
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/complexes",
        }
        if cookie.strip():
            headers["Cookie"] = cookie.strip()
        self._http = httpx.Client(
            base_url=BASE_URL, headers=headers, timeout=20, transport=transport, follow_redirects=True
        )

    # MARK: - 저수준 요청

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            self._sleep(wait + random.uniform(0, self.min_interval * 0.3))
        self._last_request = time.monotonic()

    def _fetch_token(self) -> str:
        self._throttle()
        resp = self._http.get("/complexes", headers={"Accept": "text/html"})
        m = TOKEN_RE.search(resp.text)
        if resp.status_code != 200 or not m:
            raise NaverError(
                f"네이버 부동산 접속 토큰을 가져오지 못했습니다 (HTTP {resp.status_code}). "
                "설정에서 토큰을 직접 입력해 보세요."
            )
        return m.group(1)

    def get_json(self, path: str, params: Dict[str, Any], ttl: float) -> Dict[str, Any]:
        key = f"{path}?{urlencode(sorted(params.items()))}"
        cached = self.cache.get(key, ttl)
        if cached is not None:
            return cached

        with self._lock:
            refreshed = False
            for attempt in range(4):
                if self._token is None:
                    self._token = self._fetch_token()
                self._throttle()
                try:
                    resp = self._http.get(path, params=params, headers={"Authorization": f"Bearer {self._token}"})
                except httpx.TransportError as e:
                    if attempt == 3:
                        raise NaverError(f"네이버 부동산에 연결하지 못했습니다: {e}") from e
                    self._sleep(2 ** attempt)
                    continue

                if resp.status_code == 401 and not refreshed:
                    if self._manual_token:
                        raise NaverError("입력한 토큰이 만료되었습니다. 설정에서 새 토큰을 넣거나 비워 두세요.")
                    self._token = None  # 토큰 만료 -> 새로 받아서 한 번 더
                    refreshed = True
                    continue
                if resp.status_code == 429:
                    if attempt < 3:
                        self._sleep(5 * 2 ** attempt)  # 5, 10, 20초 쉬고 다시
                    continue
                if resp.status_code >= 400:
                    raise NaverError(f"네이버 부동산 오류 (HTTP {resp.status_code}): {path}")
                try:
                    data = resp.json()
                except ValueError as e:
                    raise NaverError(f"네이버 부동산 응답을 해석하지 못했습니다: {path}") from e
                self.cache.set(key, data)
                return data
        raise NaverError("네이버 부동산이 요청을 제한하고 있습니다. 잠시 후 다시 시도하세요.")

    # MARK: - 데이터

    def regions(self, cortar_no: str = "0000000000") -> List[Region]:
        data = self.get_json("/api/regions/list", {"cortarNo": cortar_no}, TTL_REGIONS)
        return parse.regions(data)

    def complexes(self, cortar_no: str) -> List[Complex]:
        data = self.get_json(
            "/api/regions/complexes", {"cortarNo": cortar_no, "realEstateType": "APT", "order": ""}, TTL_COMPLEXES
        )
        return parse.complexes(data)

    def pyeongs(self, complex_no: str) -> List[Pyeong]:
        data = self.get_json(f"/api/complexes/{complex_no}", {"sameAddressGroup": "false"}, TTL_DETAIL)
        return parse.pyeongs(data)

    def listings(self, complex_no: str, max_pages: int = 5) -> List[Listing]:
        """매매 매물. 같은 집을 여러 중개사가 올린 건 하나로 묶는다(sameAddressGroup)."""
        result: List[Listing] = []
        for page in range(1, max_pages + 1):
            data = self.get_json(
                f"/api/articles/complex/{complex_no}",
                {
                    "realEstateType": "APT",
                    "tradeType": "A1",  # 매매
                    "tag": "::::::::",
                    "rentPriceMin": 0,
                    "rentPriceMax": 900000000,
                    "priceMin": 0,
                    "priceMax": 900000000,
                    "areaMin": 0,
                    "areaMax": 900000000,
                    "showArticle": "false",
                    "sameAddressGroup": "true",
                    "priceType": "RETAIL",
                    "page": page,
                    "complexNo": complex_no,
                    "type": "list",
                    "order": "prc",
                },
                TTL_LISTINGS,
            )
            batch = parse.listings(data, complex_no)
            result.extend(batch)
            if not data.get("isMoreData") or len(batch) < ARTICLES_PER_PAGE:
                break
        return result

    def real_trades(self, complex_no: str, pyeong: Pyeong, years: int = 3) -> List[RealTrade]:
        data = self.get_json(
            f"/api/complexes/{complex_no}/prices/real",
            {
                "complexNo": complex_no,
                "tradeType": "A1",
                "year": years,
                "priceChartChange": "false",
                "areaNo": pyeong.area_no,
                "type": "table",
            },
            TTL_REAL,
        )
        return parse.real_trades(data, pyeong.area_no, pyeong.exclusive_area)
