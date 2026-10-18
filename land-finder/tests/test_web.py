import time

import pytest
from fastapi.testclient import TestClient

from landfinder.web import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(demo=True, base_dir=tmp_path))


def test_status_and_index(client):
    assert client.get("/api/status").json() == {"source": "demo"}
    assert "집찾기" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_region_tree(client):
    sido = client.get("/api/regions").json()
    assert sido[0]["name"] == "경기도"
    gu = client.get("/api/regions", params={"cortarNo": sido[0]["cortar_no"]}).json()
    dongs = client.get("/api/regions", params={"cortarNo": gu[0]["cortar_no"]}).json()
    assert {d["type"] for d in dongs} == {"sec"}


def wait(client, job_id):
    for _ in range(100):
        job = client.get(f"/api/search/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("검색이 끝나지 않음")


def test_search_then_listings(client):
    dongs = [d["cortar_no"] for d in client.get("/api/regions", params={"cortarNo": "4113500000"}).json()]
    crit = {"cortar_nos": dongs, "price_max": 300000, "area_min": 59, "area_max": 86, "exclude_low_floor": True}
    job = wait(client, client.post("/api/search", json=crit).json()["job_id"])
    assert job["status"] == "done", job
    assert job["results"]
    no = job["results"][0]["complex"]["complex_no"]

    detail = client.post(f"/api/complexes/{no}/listings", json=crit).json()
    assert len(detail["listings"]) == job["results"][0]["matched_count"]
    assert all(row["price"] <= 300000 for row in detail["listings"])
    assert detail["url"] is None  # 데모는 네이버 링크 없음

    everything = client.post(f"/api/complexes/{no}/listings", params={"all": "true"}, json=crit).json()
    assert len(everything["listings"]) == everything["total_listings"] >= len(detail["listings"])


def test_search_without_region_warns(client):
    job = wait(client, client.post("/api/search", json={}).json()["job_id"])
    assert job["results"] == []
    assert "지역" in job["warnings"][0]


def test_settings_round_trip(client, tmp_path):
    saved = client.put("/api/settings", json={"token": " abc ", "cookie": "", "min_interval": 0.1}).json()
    assert saved == {"token": "abc", "cookie": "", "min_interval": 0.3}
    assert (tmp_path / "settings.json").exists()
    assert client.get("/api/settings").json()["token"] == "abc"


def test_unknown_job(client):
    assert client.get("/api/search/nope").status_code == 404
