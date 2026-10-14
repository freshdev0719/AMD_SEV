import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import collect
    from app.main import app

    collect.demo_seed()
    return TestClient(app)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["trades"] > 0


def test_rankings_top10(client):
    for metric in ["composite", "volume", "growth", "volume_change"]:
        resp = client.get("/rankings", params={"metric": metric})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert 0 < len(items) <= 10

    items = client.get("/rankings", params={"metric": "volume"}).json()["items"]
    volumes = [i["volume"] for i in items]
    assert volumes == sorted(volumes, reverse=True)


def test_complex_detail_and_404(client):
    cid = client.get("/rankings").json()["items"][0]["complex_id"]
    body = client.get(f"/complexes/{cid}").json()
    assert body["complex"]["id"] == cid
    assert body["stats"]["score"] is not None
    assert body["trades"]
    assert client.get("/complexes/nope").status_code == 404


def test_new_highs(client):
    items = client.get("/new-highs", params={"days": 90}).json()
    assert all(i["price"] > i["previous_high"] for i in items)
