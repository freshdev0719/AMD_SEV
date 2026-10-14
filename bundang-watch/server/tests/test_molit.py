from datetime import date
from pathlib import Path

import pytest

from app.molit import MolitError, parse_response

FIXTURE = Path(__file__).parent / "fixtures" / "apt_trade_sample.xml"


def test_parse_items():
    trades, total = parse_response(FIXTURE.read_text(encoding="utf-8"), "41135")
    assert total == 2
    first, second = trades
    assert first.complex_id == "41135-100"
    assert first.apt_name == "샘플마을쌍용"
    assert first.price == 157500
    assert first.deal_date == date(2026, 9, 2)
    assert first.area == pytest.approx(59.88)
    assert first.cancelled is False
    assert second.cancelled is True
    assert second.deal_type == "직거래"


def test_auth_error():
    xml = (
        "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
        "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
        "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
    )
    with pytest.raises(MolitError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        parse_response(xml, "41135")


def test_result_code_error():
    xml = "<response><header><resultCode>03</resultCode><resultMsg>NO_DATA</resultMsg></header></response>"
    with pytest.raises(MolitError, match="NO_DATA"):
        parse_response(xml, "41135")
