"""국토교통부 아파트 매매 실거래가 API 클라이언트.

공공데이터포털: https://www.data.go.kr/data/15126469/openapi.do
금액(dealAmount)은 만원 단위 문자열("157,500")로 내려온다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

import httpx

ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
PAGE_SIZE = 1000
OK_CODES = {"00", "000"}


class MolitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Trade:
    complex_id: str
    apt_name: str
    dong: str
    jibun: str | None
    build_year: int | None
    area: float  # 전용면적 ㎡
    floor: int | None
    deal_date: date
    price: int  # 만원
    deal_type: str | None  # 중개거래 / 직거래
    cancelled: bool  # 계약 해제 여부


def _text(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    value = el.text.strip()
    return value or None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def _parse_item(item: ET.Element, lawd_cd: str) -> Trade | None:
    name = _text(item, "aptNm")
    dong = _text(item, "umdNm")
    price = _int(_text(item, "dealAmount"))
    year, month, day = (_int(_text(item, t)) for t in ("dealYear", "dealMonth", "dealDay"))
    area_text = _text(item, "excluUseAr")
    if not (name and dong and price and year and month and day and area_text):
        return None

    jibun = _text(item, "jibun")
    # aptSeq(단지 일련번호)가 없으면 동+지번+단지명으로 대체 키를 만든다.
    complex_id = _text(item, "aptSeq") or f"{lawd_cd}-{dong}-{jibun or ''}-{name}"

    return Trade(
        complex_id=complex_id,
        apt_name=name,
        dong=dong,
        jibun=jibun,
        build_year=_int(_text(item, "buildYear")),
        area=float(area_text),
        floor=_int(_text(item, "floor")),
        deal_date=date(year, month, day),
        price=price,
        deal_type=_text(item, "dealingGbn"),
        cancelled=_text(item, "cdealType") == "O",
    )


def parse_response(xml_text: str, lawd_cd: str) -> tuple[list[Trade], int]:
    """응답 XML을 파싱해 (거래 목록, totalCount)를 돌려준다."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise MolitError(f"XML 파싱 실패: {xml_text[:200]}") from e

    # 인증키 오류 등은 OpenAPI_ServiceResponse 형식으로 온다.
    auth_msg = root.findtext(".//returnAuthMsg")
    if auth_msg:
        raise MolitError(f"API 오류: {auth_msg} ({root.findtext('.//returnReasonCode')})")

    code = root.findtext("./header/resultCode")
    if code not in OK_CODES:
        raise MolitError(f"API 오류 {code}: {root.findtext('./header/resultMsg')}")

    trades = [t for item in root.iterfind("./body/items/item") if (t := _parse_item(item, lawd_cd))]
    total = _int(root.findtext("./body/totalCount")) or 0
    return trades, total


def fetch_month(client: httpx.Client, service_key: str, lawd_cd: str, year_month: str) -> list[Trade]:
    """year_month(YYYYMM) 계약분 전체를 페이지를 넘기며 가져온다."""
    if not service_key:
        raise MolitError("MOLIT_SERVICE_KEY 환경변수가 비어 있습니다.")

    trades: list[Trade] = []
    page = 1
    while True:
        resp = client.get(
            ENDPOINT,
            params={
                "serviceKey": service_key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": year_month,
                "pageNo": page,
                "numOfRows": PAGE_SIZE,
            },
            timeout=30,
        )
        resp.raise_for_status()
        batch, total = parse_response(resp.text, lawd_cd)
        trades.extend(batch)
        if not batch or page * PAGE_SIZE >= total:
            return trades
        page += 1
