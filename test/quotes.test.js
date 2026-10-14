'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { fetchQuote, fetchQuotes, searchStocks, parseNaverBasic, trendOf } = require('../src/quotes');

function mockFetch(routes) {
  return async (url) => {
    const hit = Object.keys(routes).find((k) => url.includes(k));
    if (!hit) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => routes[hit] };
  };
}

const samsungBasic = {
  itemCode: '005930',
  stockName: '삼성전자',
  closePrice: '71,700',
  compareToPreviousClosePrice: '300',
  compareToPreviousPrice: { code: '5', text: '하락', name: 'FALLING' },
  fluctuationsRatio: '0.42',
  marketStatus: 'CLOSE',
  stockExchangeType: { nameKor: '코스피' },
};

test('네이버 시세를 파싱하고 하락이면 음수 부호를 붙인다', () => {
  const q = parseNaverBasic(samsungBasic, '005930');
  assert.equal(q.price, 71700);
  assert.equal(q.change, -300);
  assert.equal(q.changeRate, -0.42);
  assert.equal(q.direction, 'down');
  assert.equal(q.market, '코스피');
});

test('상승 코드는 up 방향이 된다', () => {
  const q = parseNaverBasic({ ...samsungBasic, compareToPreviousPrice: { code: '2' }, compareToPreviousClosePrice: '1,200' }, '005930');
  assert.equal(q.direction, 'up');
  assert.equal(q.change, 1200);
});

test('최근 종가 흐름으로 추세를 계산한다', () => {
  const t = trendOf([{ date: '2026-10-08', close: 100 }, { date: '2026-10-13', close: 110 }]);
  assert.deepEqual(t, { direction: 'up', rate: 10, days: 2 });
  assert.equal(trendOf([]), null);
});

test('시세와 최근 흐름을 함께 가져온다', async () => {
  const fetchImpl = mockFetch({
    '/005930/basic': samsungBasic,
    '/005930/price': [
      { localTradedAt: '2026-10-13', closePrice: '71,700' },
      { localTradedAt: '2026-10-10', closePrice: '72,000' },
      { localTradedAt: '2026-10-08', closePrice: '73,000' },
    ],
  });
  const q = await fetchQuote('005930', { fetchImpl });
  assert.equal(q.history[0].date, '2026-10-08');
  assert.equal(q.trend.direction, 'down');
});

test('네이버가 실패하면 Yahoo로 대체한다', async () => {
  const fetchImpl = mockFetch({
    '000660.KS': {
      chart: {
        result: [{
          meta: { regularMarketPrice: 200000, chartPreviousClose: 190000, exchangeName: 'KSC', shortName: 'SK HYNIX' },
          timestamp: [1760313600, 1760400000],
          indicators: { quote: [{ close: [195000, 200000] }] },
        }],
      },
    },
  });
  const q = await fetchQuote('000660', { fetchImpl, fallbackName: 'SK하이닉스' });
  assert.equal(q.source, 'yahoo');
  assert.equal(q.name, 'SK하이닉스');
  assert.equal(q.direction, 'up');
  assert.equal(q.change, 5000);
});

test('일부 종목이 실패해도 나머지는 반환한다', async () => {
  const fetchImpl = mockFetch({ '/005930/basic': samsungBasic });
  const { quotes } = await fetchQuotes([{ code: '005930', name: '삼성전자' }, { code: '999999', name: '없는종목' }], { fetchImpl });
  assert.equal(quotes[0].price, 71700);
  assert.ok(quotes[1].error);
});

test('잘못된 코드는 거부한다', async () => {
  await assert.rejects(fetchQuote('12'), /잘못된 종목 코드/);
});

test('종목 검색 결과를 정리한다', async () => {
  const fetchImpl = mockFetch({
    'ac.stock.naver.com': {
      items: [
        { code: '035720', name: '카카오', typeName: '코스피', nationCode: 'KOR' },
        { code: 'AAPL', name: '애플', nationCode: 'USA' },
      ],
    },
  });
  assert.deepEqual(await searchStocks('카카오', { fetchImpl }), [{ code: '035720', name: '카카오', market: '코스피' }]);
});
