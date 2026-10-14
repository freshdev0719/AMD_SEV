'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');

const { Store } = require('../src/store');
const { isDue } = require('../src/scheduler');
const { summarize } = require('../src/report');
const { createApp } = require('../server');

// KST 시각을 UTC Date로 변환
const kst = (s) => new Date(new Date(`${s}Z`).getTime() - 9 * 3600 * 1000);

test('설정한 시각부터 하루 한 번만 알림 시점이 된다', () => {
  const settings = { enabled: true, time: '08:30', weekdaysOnly: true };
  assert.equal(isDue(settings, null, kst('2026-10-14T08:29')), false);
  assert.equal(isDue(settings, null, kst('2026-10-14T08:30')), true);
  assert.equal(isDue(settings, '2026-10-14', kst('2026-10-14T09:00')), false);
  assert.equal(isDue(settings, null, kst('2026-10-14T15:00')), false); // 너무 늦으면 건너뜀
  assert.equal(isDue(settings, null, kst('2026-10-17T08:30')), false); // 토요일
  assert.equal(isDue({ ...settings, weekdaysOnly: false }, null, kst('2026-10-17T08:30')), true);
  assert.equal(isDue({ ...settings, enabled: false }, null, kst('2026-10-14T08:30')), false);
});

test('리포트 요약 문구', () => {
  const s = summarize({
    quotes: [
      { name: '삼성전자', price: 71700, changeRate: -0.42, direction: 'down' },
      { name: 'SK하이닉스', price: 200000, changeRate: 2.63, direction: 'up' },
      { code: '123456', name: 'X', error: 'fail' },
    ],
  });
  assert.equal(s.title, '오늘의 아침 시세 · 상승 1 / 하락 1');
  assert.match(s.body, /▼ 삼성전자 71,700원 \(-0\.42%\)/);
  assert.match(s.body, /▲ SK하이닉스 200,000원 \(\+2\.63%\)/);
});

async function withServer(fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'stock-'));
  const store = new Store(path.join(dir, 'store.json'));
  const sent = [];
  const pusher = { publicKey: 'pk', sendAll: async (p) => { sent.push(p); return { sent: 0, total: 0 }; } };
  const app = createApp({
    store,
    pusher,
    quoteFetcher: async (stocks) => ({
      fetchedAt: new Date().toISOString(),
      quotes: stocks.map((s) => ({ ...s, price: 1000, change: 10, changeRate: 1, direction: 'up' })),
    }),
    quoteLookup: async (code) => {
      if (code === '035720') return { name: '카카오' };
      throw new Error('nope');
    },
    search: async () => [],
  });
  const server = http.createServer(app.handle);
  await new Promise((r) => server.listen(0, r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (method, p, body) => {
    const res = await fetch(base + p, { method, body: body && JSON.stringify(body) });
    return { status: res.status, body: await res.json() };
  };
  try {
    await fn({ call, store, sent, base });
  } finally {
    server.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test('기본 종목은 삼성전자와 SK하이닉스', async () => {
  await withServer(async ({ call }) => {
    const { body } = await call('GET', '/api/quotes');
    assert.deepEqual(body.quotes.map((q) => q.code), ['005930', '000660']);
  });
});

test('종목 추가/중복/삭제', async () => {
  await withServer(async ({ call, store }) => {
    assert.deepEqual((await call('POST', '/api/stocks', { code: '035720' })).body, { code: '035720', name: '카카오' });
    assert.equal((await call('POST', '/api/stocks', { code: '035720' })).status, 409);
    assert.equal((await call('POST', '/api/stocks', { code: '111111' })).status, 404);
    assert.equal((await call('POST', '/api/stocks', { code: 'abc' })).status, 400);
    const { body } = await call('GET', '/api/quotes');
    assert.equal(body.quotes.length, 3);
    assert.equal((await call('DELETE', '/api/stocks/035720')).status, 200);
    assert.equal(store.stocks.length, 2);
    // 파일에 저장되어 재시작 후에도 유지된다
    assert.equal(new Store(store.file).stocks.length, 2);
  });
});

test('설정 변경 검증과 리포트 실행', async () => {
  await withServer(async ({ call, sent }) => {
    assert.equal((await call('PUT', '/api/settings', { time: '25:00' })).status, 400);
    assert.equal((await call('PUT', '/api/settings', { time: '07:45', weekdaysOnly: false })).body.time, '07:45');
    const run = await call('POST', '/api/report/run');
    assert.equal(run.status, 200);
    assert.equal(sent.length, 1);
    assert.match(sent[0].title, /상승 2/);
    assert.equal((await call('GET', '/api/report')).body.title, sent[0].title);
  });
});

test('정적 파일 제공과 경로 탈출 차단', async () => {
  await withServer(async ({ base }) => {
    const res = await fetch(`${base}/`);
    assert.equal(res.status, 200);
    assert.match(await res.text(), /아침 주식 알리미/);
    const bad = await fetch(`${base}/..%2fpackage.json`);
    assert.notEqual(bad.status, 200);
  });
});
