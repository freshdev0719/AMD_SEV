# 분당 실거래 모니터 (Bundang Watch)

국토교통부 아파트 매매 실거래가를 매일 수집해서 분당구 단지를 **거래량 / 가격 상승률 / 거래량 증가율 / 종합 점수**로 순위를 매기고, 아이폰 앱으로 보여줍니다.

```
┌──────────────┐  매일 수집   ┌─────────────────────┐   JSON   ┌───────────────┐
│ 국토부 실거래 │ ───────────▶ │ server (FastAPI +   │ ───────▶ │ iOS 앱        │
│ API (data.go.kr)│ collect.py │ SQLite, 순위 계산)  │          │ (SwiftUI)     │
└──────────────┘              └─────────────────────┘          └───────────────┘
```

서비스 키를 앱 안에 넣지 않으려고 서버를 둡니다. 순위 계산도 서버에서 합니다.

## 1. 서버

### 준비

1. [공공데이터포털 – 국토교통부 아파트 매매 실거래가 자료](https://www.data.go.kr/data/15126469/openapi.do)에서 활용 신청을 합니다(개발계정은 보통 바로 승인).
2. 마이페이지에서 **일반 인증키(Decoding)** 값을 복사합니다. Encoding 키를 넣으면 두 번 인코딩되어 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 납니다.

### 실행

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

export MOLIT_SERVICE_KEY='발급받은 Decoding 키'
python collect.py backfill --months 36   # 처음 한 번 (3년치, 약 36회 호출)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API 키 없이 화면만 먼저 보고 싶으면 `python collect.py demo-seed`로 가짜 데이터(단지명이 "데모단지 A"처럼 나옴)를 넣을 수 있습니다. 실제 데이터를 쓰기 전에 `data/trades.db`를 지우세요.

### 매일 수집 (cron 예시)

실거래 신고 기한이 계약 후 30일이고 계약 해제도 나중에 반영되므로, 최근 3개월치를 매일 다시 받아 덮어씁니다.

```cron
# 매일 06:10 KST
10 6 * * * cd /path/to/server && MOLIT_SERVICE_KEY=... .venv/bin/python collect.py refresh >> collect.log 2>&1
```

### API

| 엔드포인트 | 설명 |
|---|---|
| `GET /rankings?metric=composite\|volume\|growth\|volume_change&limit=10` | TOP N 단지 |
| `GET /complexes/{id}` | 단지 정보, 지표, 최근 3년 거래(신고가 표시 포함) |
| `GET /new-highs?days=30` | 최근 신고가 거래 |
| `GET /health` | 저장된 거래 수, 마지막 수집 시각 |

`/rankings`는 `window_days`(기본 90), `exclude_direct`(기본 true), `as_of`(기준일)도 받습니다. 브라우저에서 `http://localhost:8000/docs`를 열면 바로 호출해 볼 수 있습니다.

### 지표 계산 방식 (`server/app/ranking.py`)

- **유효 거래**: 계약 해제 건은 항상 빼고, 직거래는 기본으로 뺍니다(가족 간 거래 등 시세와 동떨어진 경우가 많아서).
- **거래량**: 최근 90일 유효 거래 건수.
- **거래량 증가율**: 1년 전 같은 90일 대비 건수 변화.
- **가격 상승률**: 같은 단지·같은 전용면적(㎡ 반올림)끼리 최근 90일 중위가격을 1년 전 같은 기간과 비교하고, 면적별 결과를 표본 수로 가중 평균합니다. 최근에 큰 평형만 팔려서 상승률이 부풀려지는 일을 막기 위해서입니다. 비교할 표본이 2건 미만이면 계산하지 않습니다.
- **종합 점수**: 상승률을 계산할 수 있는 단지 중에서 거래량 백분위와 상승률 백분위를 50:50으로 합칩니다.
- **신고가**: 같은 단지·같은 면적에서 그 날짜 이전 모든 거래보다 비싼 거래입니다.

최근 30일 정도는 아직 신고되지 않은 거래가 있어서 거래량과 거래량 증가율이 실제보다 낮게 나옵니다. 정확한 비교가 필요하면 `as_of`를 한 달 전으로 지정하세요.

### 테스트

```bash
cd server && pytest
```

### 배포

`server/Dockerfile`로 Fly.io, Render, Railway, 아무 VM에나 올릴 수 있습니다. `/data`를 영구 볼륨으로 붙이고, 같은 컨테이너나 별도 스케줄러에서 `python collect.py refresh`를 매일 돌리면 됩니다. 앱에서 붙을 주소는 반드시 HTTPS여야 합니다.

## 2. iOS 앱 (`ios/BundangWatch`)

iOS 17 이상, SwiftUI + Swift Charts. 외부 라이브러리는 없습니다.

```bash
brew install xcodegen
cd ios/BundangWatch
xcodegen          # BundangWatch.xcodeproj 생성
open BundangWatch.xcodeproj
```

XcodeGen을 쓰기 싫으면 Xcode에서 새 iOS App 프로젝트(SwiftUI, iOS 17)를 만들고 `Sources` 폴더의 파일을 끌어다 넣은 뒤, 기본으로 생긴 `App`/`ContentView` 파일을 지우고 Info.plist에 `NSAppTransportSecurity > NSAllowsLocalNetworking = YES`를 추가하면 됩니다.

- 시뮬레이터: 서버를 Mac에서 띄우면 기본 주소(`http://localhost:8000`)로 바로 동작합니다.
- 실제 아이폰: 같은 Wi‑Fi에서 **설정 탭**에 Mac의 IP(예: `http://192.168.0.10:8000`)를 넣거나, 배포한 HTTPS 주소를 넣습니다.

| 탭 | 내용 |
|---|---|
| 랭킹 | 종합·거래량·상승률·거래증가 기준 TOP 10 |
| 신고가 | 최근 7/30/90일 신고가 거래 |
| 관심단지 | 단지 상세에서 ☆로 추가한 단지 (기기에 저장) |
| 설정 | 서버 주소, 연결 확인, 지표 설명 |

단지 상세 화면에는 지표 요약, 면적별 가격 추이 차트, 최근 거래 목록(신고가·직거래·해제 표시)이 나옵니다.

## 다음 단계 아이디어

- 관심 단지에 신고가가 나오면 푸시 알림 (APNs 키 등록 → 서버에서 refresh 후 발송)
- 분당 외 지역 선택 (`LAWD_CD` 파라미터화)
- 전세가율, 호가(매물) 데이터 추가

> 실거래 공개 자료를 집계한 참고 정보일 뿐 투자 권유가 아닙니다.
