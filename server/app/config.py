import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

# 한국은 서머타임이 없어 고정 오프셋으로 충분하다 (tzdata 없는 컨테이너에서도 동작).
KST = timezone(timedelta(hours=9))

# 성남시 분당구 법정동 시군구 코드
BUNDANG_LAWD_CD = "41135"


@dataclass(frozen=True)
class Settings:
    service_key: str
    db_path: str
    lawd_cd: str


def load_settings() -> Settings:
    return Settings(
        service_key=os.environ.get("MOLIT_SERVICE_KEY", ""),
        db_path=os.environ.get("DB_PATH", "data/trades.db"),
        lawd_cd=os.environ.get("LAWD_CD", BUNDANG_LAWD_CD),
    )


def today_kst() -> date:
    return datetime.now(KST).date()
