'use strict';

// 네이버 증권 모바일 API에서 국내 주식 시세를 가져온다.
// 실패하면 Yahoo Finance(코스피 .KS / 코스닥 .KQ)로 한 번 더 시도한다.

const NAVER_BASE = 'https://m.stock.naver.com/api/stock';
const NAVER_SEARCH = 'https://ac.stock.naver.com/ac';
const YAHOO_CHART = 'https://query1.finance.yahoo.com/v8/finance/chart';

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (morning-stock-alert)',
  Accept: 'application/json',
};

const TIMEOUT_MS = 8000;

// 네이버 compareToPreviousPrice.code: 1 상한, 2 상승, 3 보합, 4 하한, 5 하락
const NAVER_DIRECTION = { 1: 'up', 2: 'up', 3: 'flat', 4: 'down', 5: 'down' };

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const n = Number(String(value).replace(/,/g, '').trim());
  return Number.isFinite(n) ? n : null;
}

function directionOf(change) {
  if (change > 0) return 'up';
  if (change < 0) return 'down';
  return 'flat';
}

function isValidCode(code) {
  return /^[0-9A-Z]{6}$/.test(String(code));
}

async function fetchJson(url, fetchImpl = fetch) {
  const res = await fetchImpl(url, {
    headers: HEADERS,
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} (${url})`);
  return res.json();
}

function parseNaverBasic(json, code) {
  const price = toNumber(json.closePrice);
  if (price === null) throw new Error(`시세 정보가 없습니다 (${code})`);

  const rawChange = toNumber(json.compareToPreviousClosePrice) ?? 0;
  const rawRate = toNumber(json.fluctuationsRatio) ?? 0;
  const dirCode = json.compareToPreviousPrice && json.compareToPreviousPrice.code;
  const direction = NAVER_DIRECTION[dirCode] || directionOf(rawChange || rawRate);

  // 네이버는 하락 시 부호가 붙지 않는 경우도 있어 방향 기준으로 부호를 맞춘다.
  const sign = direction === 'down' ? -1 : direction === 'up' ? 1 : 0;
  return {
    code,
    name: json.stockName || code,
    market: (json.stockExchangeType && json.stockExchangeType.nameKor) || json.stockExchangeName || '',
    price,
    change: sign * Math.abs(rawChange),
    changeRate: sign * Math.abs(rawRate),
    direction,
    marketStatus: json.marketStatus || null,
    tradedAt: json.localTradedAt || null,
    source: 'naver',
  };
}

function parseNaverHistory(json) {
  const rows = Array.isArray(json) ? json : (json && json.priceInfos) || [];
  return rows
    .map((row) => ({
      date: String(row.localTradedAt || '').slice(0, 10),
      close: toNumber(row.closePrice),
    }))
    .filter((row) => row.date && row.close !== null)
    .sort((a, b) => a.date.localeCompare(b.date));
}

function parseYahooChart(json, code) {
  const result = json && json.chart && json.chart.result && json.chart.result[0];
  if (!result || !result.meta) throw new Error(`시세 정보가 없습니다 (${code})`);
  const meta = result.meta;
  const price = toNumber(meta.regularMarketPrice);
  const prev = toNumber(meta.chartPreviousClose ?? meta.previousClose);
  if (price === null) throw new Error(`시세 정보가 없습니다 (${code})`);

  const timestamps = result.timestamp || [];
  const closes = (result.indicators && result.indicators.quote && result.indicators.quote[0]
    && result.indicators.quote[0].close) || [];
  const history = timestamps
    .map((t, i) => ({
      date: new Date((t + 9 * 3600) * 1000).toISOString().slice(0, 10),
      close: toNumber(closes[i]),
    }))
    .filter((row) => row.close !== null);

  // 일봉 기준 전일 종가가 있으면 그것을, 없으면 메타 정보의 이전 종가를 쓴다.
  const prevClose = history.length >= 2 ? history[history.length - 2].close : prev;
  const change = prevClose ? price - prevClose : 0;
  const changeRate = prevClose ? (change / prevClose) * 100 : 0;

  return {
    quote: {
      code,
      name: meta.longName || meta.shortName || code,
      market: meta.exchangeName === 'KOE' ? '코스닥' : '코스피',
      price,
      change: Math.round(change * 100) / 100,
      changeRate: Math.round(changeRate * 100) / 100,
      direction: directionOf(change),
      marketStatus: null,
      tradedAt: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
      source: 'yahoo',
    },
    history,
  };
}

// 최근 종가 흐름으로 단기 추세를 판단한다 (첫 종가 대비 마지막 종가).
function trendOf(history) {
  if (!history || history.length < 2) return null;
  const first = history[0].close;
  const last = history[history.length - 1].close;
  const rate = first ? ((last - first) / first) * 100 : 0;
  return { direction: directionOf(last - first), rate: Math.round(rate * 100) / 100, days: history.length };
}

async function fetchFromNaver(code, fetchImpl) {
  const basic = await fetchJson(`${NAVER_BASE}/${code}/basic`, fetchImpl);
  const quote = parseNaverBasic(basic, code);
  let history = [];
  try {
    const raw = await fetchJson(`${NAVER_BASE}/${code}/price?pageSize=5&page=1`, fetchImpl);
    history = parseNaverHistory(raw);
  } catch {
    // 추세 데이터는 부가 정보이므로 실패해도 시세는 보여준다.
  }
  return { quote, history };
}

async function fetchFromYahoo(code, fetchImpl) {
  let lastError;
  for (const suffix of ['KS', 'KQ']) {
    try {
      const json = await fetchJson(`${YAHOO_CHART}/${code}.${suffix}?range=5d&interval=1d`, fetchImpl);
      return parseYahooChart(json, code);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

async function fetchQuote(code, { fetchImpl = fetch, fallbackName } = {}) {
  if (!isValidCode(code)) throw new Error(`잘못된 종목 코드입니다: ${code}`);
  let result;
  try {
    result = await fetchFromNaver(code, fetchImpl);
  } catch (naverError) {
    try {
      result = await fetchFromYahoo(code, fetchImpl);
    } catch {
      throw naverError;
    }
  }
  const { quote, history } = result;
  if (fallbackName && (quote.name === code || quote.source === 'yahoo')) quote.name = fallbackName;
  return { ...quote, history, trend: trendOf(history) };
}

async function fetchQuotes(stocks, options = {}) {
  const results = await Promise.all(
    stocks.map(async (stock) => {
      try {
        return await fetchQuote(stock.code, { ...options, fallbackName: stock.name });
      } catch (err) {
        return { code: stock.code, name: stock.name, error: err.message };
      }
    }),
  );
  return { fetchedAt: new Date().toISOString(), quotes: results };
}

async function searchStocks(query, { fetchImpl = fetch } = {}) {
  const q = String(query || '').trim();
  if (!q) return [];
  const url = `${NAVER_SEARCH}?q=${encodeURIComponent(q)}&target=stock`;
  const json = await fetchJson(url, fetchImpl);
  const items = (json && json.items) || [];
  return items
    .filter((item) => (item.nationCode || 'KOR') === 'KOR' && isValidCode(item.code))
    .slice(0, 10)
    .map((item) => ({ code: item.code, name: item.name, market: item.typeName || item.typeCode || '' }));
}

module.exports = {
  fetchQuote,
  fetchQuotes,
  searchStocks,
  isValidCode,
  // 테스트용
  parseNaverBasic,
  parseNaverHistory,
  parseYahooChart,
  trendOf,
  toNumber,
};
