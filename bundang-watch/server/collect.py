"""실거래 데이터 수집 CLI.

    python collect.py backfill --months 36   # 처음 한 번: 과거 3년치
    python collect.py refresh                # 매일: 최근 3개월치 다시 받기
    python collect.py demo-seed              # API 키 없이 앱을 띄워 볼 가짜 데이터

실거래 신고 기한은 계약 후 30일이고 계약 해제도 나중에 반영되므로,
refresh는 최근 몇 달을 매번 통째로 다시 받아 덮어쓴다.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date, timedelta

import httpx

from app import db
from app.config import load_settings, today_kst
from app.molit import MolitError, Trade, fetch_month


def recent_months(count: int, today: date) -> list[str]:
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


def collect(months: int) -> int:
    settings = load_settings()
    conn = db.connect(settings.db_path)
    total = 0
    with httpx.Client() as client:
        for ym in recent_months(months, today_kst()):
            for attempt in range(4):
                try:
                    trades = fetch_month(client, settings.service_key, settings.lawd_cd, ym)
                    break
                except (httpx.TransportError, httpx.HTTPStatusError) as e:
                    if attempt == 3:
                        raise
                    wait = 2 ** (attempt + 1)
                    print(f"{ym}: {e} — {wait}초 후 재시도", file=sys.stderr)
                    time.sleep(wait)
            db.upsert_trades(conn, trades)
            db.log_collect(conn, ym, len(trades))
            total += len(trades)
            print(f"{ym}: {len(trades)}건")
    conn.close()
    return total


DEMO_DONGS = ["수내동", "정자동", "서현동", "이매동", "야탑동", "분당동", "금곡동", "구미동", "백현동", "삼평동"]


def demo_seed(seed: int = 42) -> int:
    """화면 확인용 가짜 데이터. 단지명은 일부러 실제와 겹치지 않게 '데모'를 붙인다."""
    rng = random.Random(seed)
    settings = load_settings()
    conn = db.connect(settings.db_path)
    today = today_kst()
    trades: list[Trade] = []
    for i in range(30):
        cid = f"DEMO-{i:02d}"
        name = f"데모단지 {chr(ord('A') + i % 26)}{i // 26 or ''}"
        dong = DEMO_DONGS[i % len(DEMO_DONGS)]
        build_year = rng.randint(1992, 2015)
        areas = rng.sample([39.6, 59.9, 84.9, 101.8, 134.5], k=rng.randint(1, 3))
        base = {a: a * rng.uniform(1300, 2200) for a in areas}  # 만원
        yearly_growth = rng.uniform(-0.05, 0.35)
        trades_per_month = rng.uniform(0.3, 4.0)
        for days_ago in range(3 * 365, -1, -1):
            if rng.random() > trades_per_month / 30:
                continue
            d = today - timedelta(days=days_ago)
            area = rng.choice(areas)
            years_from_start = (3 * 365 - days_ago) / 365
            price = base[area] * (1 + yearly_growth) ** years_from_start * rng.uniform(0.94, 1.06)
            trades.append(
                Trade(
                    complex_id=cid,
                    apt_name=name,
                    dong=dong,
                    jibun=None,
                    build_year=build_year,
                    area=area,
                    floor=rng.randint(1, 25),
                    deal_date=d,
                    price=int(round(price, -2)),
                    deal_type="직거래" if rng.random() < 0.05 else "중개거래",
                    cancelled=rng.random() < 0.03,
                )
            )
    db.upsert_trades(conn, trades)
    db.log_collect(conn, "DEMO", len(trades))
    conn.close()
    return len(trades)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backfill").add_argument("--months", type=int, default=36)
    sub.add_parser("refresh").add_argument("--months", type=int, default=3)
    sub.add_parser("demo-seed")
    args = parser.parse_args()

    try:
        if args.command == "demo-seed":
            print(f"데모 거래 {demo_seed()}건 저장")
        else:
            print(f"총 {collect(args.months)}건 저장")
    except MolitError as e:
        sys.exit(f"수집 실패: {e}")


if __name__ == "__main__":
    main()
