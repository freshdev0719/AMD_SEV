import httpx
import pytest

from landfinder.cache import Cache
from landfinder.naver import NaverError, NaverLandClient

PAGE_HTML = '<script>window.__APP__={"token":"tok-1","other":1}</script>'


class FakeNaver:
    """요청을 기록하고 미리 정한 응답을 돌려주는 가짜 네이버."""

    def __init__(self, routes):
        self.routes = routes  # path -> list of (status, body) 또는 callable
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url.path == "/complexes":
            return httpx.Response(200, text=PAGE_HTML)
        queue = self.routes[request.url.path]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        if callable(body):
            body = body(request)
        return httpx.Response(status, json=body)


def make_client(fake, **kwargs):
    sleeps = []
    client = NaverLandClient(
        Cache(":memory:"), transport=httpx.MockTransport(fake), sleep=sleeps.append, min_interval=0, **kwargs
    )
    return client, sleeps


def test_fetches_token_and_sends_bearer(load):
    fake = FakeNaver({"/api/regions/complexes": [(200, load("complexes.json"))]})
    client, _ = make_client(fake)
    items = client.complexes("4113510900")
    assert len(items) == 2
    api_call = fake.calls[-1]
    assert api_call.headers["authorization"] == "Bearer tok-1"
    assert api_call.url.params["cortarNo"] == "4113510900"
    assert api_call.url.params["realEstateType"] == "APT"


def test_results_are_cached(load):
    fake = FakeNaver({"/api/regions/complexes": [(200, load("complexes.json"))]})
    client, _ = make_client(fake)
    client.complexes("4113510900")
    client.complexes("4113510900")
    assert sum(1 for c in fake.calls if c.url.path == "/api/regions/complexes") == 1


def test_refreshes_token_on_401(load):
    fake = FakeNaver({"/api/regions/list": [(401, {}), (200, {"regionList": [{"cortarNo": "1", "cortarName": "가"}]})]})
    client, _ = make_client(fake)
    assert [r.name for r in client.regions()] == ["가"]
    assert sum(1 for c in fake.calls if c.url.path == "/complexes") == 2


def test_manual_token_is_not_refreshed():
    fake = FakeNaver({"/api/regions/list": [(401, {})]})
    client, _ = make_client(fake, token="mine")
    with pytest.raises(NaverError, match="토큰이 만료"):
        client.regions()
    assert fake.calls[0].headers["authorization"] == "Bearer mine"


def test_backs_off_on_429_then_gives_up():
    fake = FakeNaver({"/api/regions/list": [(429, {})]})
    client, sleeps = make_client(fake)
    with pytest.raises(NaverError, match="제한"):
        client.regions()
    assert [s for s in sleeps if s >= 5] == [5, 10, 20]


def test_listings_paginate(load):
    page1 = load("articles_p1.json")
    page1["articleList"] = page1["articleList"] * 7  # 21건 -> 다음 페이지 있음
    page2 = {"isMoreData": False, "articleList": [{"articleNo": "9", "dealOrWarrantPrc": "1억"}]}
    fake = FakeNaver({"/api/articles/complex/1001": [(200, lambda r: page1 if r.url.params["page"] == "1" else page2)]})
    client, _ = make_client(fake)
    items = client.listings("1001")
    assert len(items) == 22
    pages = [c.url.params["page"] for c in fake.calls if c.url.path.startswith("/api/articles")]
    assert pages == ["1", "2"]
    assert fake.calls[-1].url.params["tradeType"] == "A1"


def test_missing_token_gives_clear_error():
    def handler(request):
        return httpx.Response(200, text="<html>no token</html>")

    client = NaverLandClient(Cache(":memory:"), transport=httpx.MockTransport(handler), sleep=lambda s: None, min_interval=0)
    with pytest.raises(NaverError, match="토큰"):
        client.regions()
