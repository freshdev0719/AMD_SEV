from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import db
from .config import load_settings, today_kst
from .ranking import ComplexStats, Metric, area_bucket, compute_stats, find_new_highs, is_valid, rank

app = FastAPI(title="Bundang Watch API", version="0.1.0")


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = db.connect(load_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


class RankingItem(BaseModel):
    complex_id: str
    name: str
    dong: str
    build_year: int | None
    volume: int
    prior_volume: int
    volume_change: float | None
    growth: float | None
    score: float | None
    new_highs: int
    latest_price: int | None
    latest_deal_date: date | None
    latest_area: float | None


class RankingResponse(BaseModel):
    as_of: date
    metric: Metric
    window_days: int
    last_collected_at: str | None
    items: list[RankingItem]


class TradeItem(BaseModel):
    deal_date: date
    area: float
    area_bucket: int
    floor: int | None
    price: int
    deal_type: str | None
    cancelled: bool
    previous_high: int | None


class ComplexInfo(BaseModel):
    id: str
    name: str
    dong: str
    jibun: str | None
    build_year: int | None


class ComplexDetail(BaseModel):
    complex: ComplexInfo
    stats: RankingItem | None
    trades: list[TradeItem]


class NewHighItem(BaseModel):
    complex_id: str
    name: str
    dong: str
    deal_date: date
    area: float
    floor: int | None
    price: int
    previous_high: int
    increase: float


def _ranking_item(s: ComplexStats, complex_row: sqlite3.Row) -> RankingItem:
    return RankingItem(
        complex_id=s.complex_id,
        name=complex_row["name"],
        dong=complex_row["dong"],
        build_year=complex_row["build_year"],
        volume=s.volume,
        prior_volume=s.prior_volume,
        volume_change=s.volume_change,
        growth=s.growth,
        score=s.score,
        new_highs=s.new_highs,
        latest_price=s.latest.price if s.latest else None,
        latest_deal_date=s.latest.deal_date if s.latest else None,
        latest_area=s.latest.area if s.latest else None,
    )


@app.get("/health")
def health(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    return {"status": "ok", "trades": count, "last_collected_at": db.last_collected_at(conn)}


@app.get("/rankings", response_model=RankingResponse)
def rankings(
    metric: Metric = Metric.composite,
    limit: int = Query(10, ge=1, le=100),
    window_days: int = Query(90, ge=30, le=365),
    exclude_direct: bool = True,
    as_of: date | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> RankingResponse:
    as_of = as_of or today_kst()
    stats = compute_stats(db.load_trades(conn), as_of, window_days, exclude_direct)
    complexes = db.load_complexes(conn)
    return RankingResponse(
        as_of=as_of,
        metric=metric,
        window_days=window_days,
        last_collected_at=db.last_collected_at(conn),
        items=[_ranking_item(s, complexes[s.complex_id]) for s in rank(stats, metric, limit)],
    )


@app.get("/complexes/{complex_id}", response_model=ComplexDetail)
def complex_detail(
    complex_id: str,
    years: int = Query(3, ge=1, le=20),
    window_days: int = Query(90, ge=30, le=365),
    exclude_direct: bool = True,
    conn: sqlite3.Connection = Depends(get_conn),
) -> ComplexDetail:
    row = db.get_complex(conn, complex_id)
    if row is None:
        raise HTTPException(404, "단지를 찾을 수 없습니다.")

    as_of = today_kst()
    # 종합 점수는 다른 단지와의 상대 순위라 전체 거래로 계산한다.
    stats = compute_stats(db.load_trades(conn), as_of, window_days, exclude_direct).get(complex_id)
    trades = db.load_trades(conn, complex_id)
    highs = find_new_highs([t for t in trades if is_valid(t, exclude_direct)])
    since = as_of - timedelta(days=365 * years)

    return ComplexDetail(
        complex=ComplexInfo(
            id=row["id"], name=row["name"], dong=row["dong"], jibun=row["jibun"], build_year=row["build_year"]
        ),
        stats=_ranking_item(stats, row) if stats else None,
        trades=[
            TradeItem(
                deal_date=t.deal_date,
                area=t.area,
                area_bucket=area_bucket(t.area),
                floor=t.floor,
                price=t.price,
                deal_type=t.deal_type,
                cancelled=t.cancelled,
                previous_high=highs.get(t.id),
            )
            for t in sorted(trades, key=lambda t: t.deal_date, reverse=True)
            if t.deal_date >= since
        ],
    )


@app.get("/new-highs", response_model=list[NewHighItem])
def new_highs(
    days: int = Query(30, ge=1, le=365),
    exclude_direct: bool = True,
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[NewHighItem]:
    since = today_kst() - timedelta(days=days)
    trades = [t for t in db.load_trades(conn) if is_valid(t, exclude_direct)]
    highs = find_new_highs(trades)
    complexes = db.load_complexes(conn)
    items = [
        NewHighItem(
            complex_id=t.complex_id,
            name=complexes[t.complex_id]["name"],
            dong=complexes[t.complex_id]["dong"],
            deal_date=t.deal_date,
            area=t.area,
            floor=t.floor,
            price=t.price,
            previous_high=highs[t.id],
            increase=t.price / highs[t.id] - 1,
        )
        for t in trades
        if t.id in highs and t.deal_date >= since
    ]
    items.sort(key=lambda i: (i.deal_date, i.increase), reverse=True)
    return items
