"""앱 화면(로컬 웹페이지)과 화면이 부르는 API."""

from __future__ import annotations

import json
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import search as search_mod
from .cache import Cache
from .demo import DemoSource
from .models import to_dict
from .naver import NaverError, NaverLandClient, complex_url

STATIC_DIR = Path(__file__).parent / "static"


def data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LandFinder"
    return Path.home() / ".landfinder"


@dataclass
class Settings:
    token: str = ""
    cookie: str = ""
    min_interval: float = 1.0  # 네이버 요청 사이 최소 간격(초)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(
            token=str(data.get("token", "")),
            cookie=str(data.get("cookie", "")),
            min_interval=max(0.3, float(data.get("min_interval", 1.0))),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class Job:
    id: str
    status: str = "running"  # running / done / error
    message: str = "시작하는 중"
    done: int = 0
    total: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    cancel: bool = False

    def view(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("cancel")
        return data


def create_app(demo: bool = False, base_dir: Optional[Path] = None) -> FastAPI:
    base = base_dir or data_dir()
    settings_path = base / "settings.json"
    cache = Cache(str(base / "cache.sqlite"))
    state: Dict[str, Any] = {"settings": Settings.load(settings_path)}

    def make_source() -> Any:
        if demo:
            return DemoSource()
        s = state["settings"]
        return NaverLandClient(cache, token=s.token, cookie=s.cookie, min_interval=s.min_interval)

    state["source"] = make_source()
    jobs: Dict[str, Job] = {}

    app = FastAPI(title="LandFinder", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def call(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except NaverError as e:
            raise HTTPException(502, str(e)) from e

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> Dict[str, Any]:
        return {"source": state["source"].name}

    @app.get("/api/settings")
    def get_settings() -> Dict[str, Any]:
        return asdict(state["settings"])

    @app.put("/api/settings")
    def put_settings(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        s = Settings(
            token=str(body.get("token", "")).strip(),
            cookie=str(body.get("cookie", "")).strip(),
            min_interval=max(0.3, float(body.get("min_interval") or 1.0)),
        )
        s.save(settings_path)
        state["settings"] = s
        state["source"] = make_source()
        return asdict(s)

    @app.post("/api/cache/clear")
    def clear_cache() -> Dict[str, Any]:
        cache.clear()
        return {"ok": True}

    @app.get("/api/regions")
    def regions(cortarNo: str = "0000000000") -> List[Dict[str, Any]]:
        return [to_dict(r) for r in call(lambda: state["source"].regions(cortarNo))]

    @app.post("/api/search")
    def start_search(body: Dict[str, Any] = Body(...)) -> Dict[str, str]:
        crit = search_mod.Criteria.from_dict(body)
        job = Job(id=uuid.uuid4().hex)
        jobs[job.id] = job
        source = state["source"]

        def progress(message: str, done: int, total: int) -> None:
            job.message, job.done, job.total = message, done, total

        def run() -> None:
            try:
                outcome = search_mod.search(source, crit, progress, lambda: job.cancel)
                job.results, job.warnings = outcome.results, outcome.warnings
                job.status = "done"
            except Exception as e:  # 화면에 오류를 보여주고 앱은 계속 동작하게 한다
                job.error = f"{type(e).__name__}: {e}"
                job.status = "error"

        threading.Thread(target=run, daemon=True).start()
        return {"job_id": job.id}

    @app.get("/api/search/{job_id}")
    def get_search(job_id: str) -> Dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "검색 작업을 찾을 수 없습니다.")
        return job.view()

    @app.delete("/api/search/{job_id}")
    def cancel_search(job_id: str) -> Dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "검색 작업을 찾을 수 없습니다.")
        job.cancel = True
        return {"ok": True}

    @app.post("/api/complexes/{complex_no}/listings")
    def listings(
        complex_no: str, body: Dict[str, Any] = Body(...), show_all: bool = Query(False, alias="all")
    ) -> Dict[str, Any]:
        crit = search_mod.Criteria.from_dict(body)
        data = call(lambda: search_mod.complex_listings(state["source"], complex_no, crit, apply_filter=not show_all))
        data["url"] = complex_url(complex_no) if state["source"].name == "naver" else None
        for row in data["listings"]:
            row["url"] = complex_url(complex_no, row["article_no"]) if data["url"] else None
        return data

    return app
