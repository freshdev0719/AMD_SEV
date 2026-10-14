'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const { Store } = require('./src/store');
const { fetchQuotes, fetchQuote, searchStocks, isValidCode } = require('./src/quotes');
const { startScheduler } = require('./src/scheduler');
const { summarize } = require('./src/report');
const { createPusher } = require('./src/push');

const PORT = Number(process.env.PORT) || 3000;
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const PUBLIC_DIR = path.join(__dirname, 'public');
const QUOTE_CACHE_MS = 30 * 1000;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json',
  '.json': 'application/json; charset=utf-8',
};

function createApp({ store, pusher, quoteFetcher = fetchQuotes, quoteLookup = fetchQuote, search = searchStocks }) {
  let cache = null;

  async function getQuotes(force = false) {
    if (!force && cache && Date.now() - cache.at < QUOTE_CACHE_MS && cache.key === key()) return cache.value;
    const value = await quoteFetcher(store.stocks);
    cache = { at: Date.now(), key: key(), value };
    return value;
  }
  function key() {
    return store.stocks.map((s) => s.code).join(',');
  }

  // 아침 리포트를 만들고 구독자에게 푸시 알림을 보낸다.
  async function runMorningReport(runDate) {
    const snapshot = await getQuotes(true);
    const summary = summarize(snapshot);
    const report = { ...snapshot, ...summary };
    store.setReport(report, runDate);
    const result = await pusher.sendAll({ title: summary.title, body: summary.body, url: '/' });
    return { report, push: result };
  }

  const routes = {
    'GET /api/quotes': async (req, url) => getQuotes(url.searchParams.get('refresh') === '1'),
    'GET /api/stocks': async () => store.stocks,
    'POST /api/stocks': async (req) => {
      const body = await readJson(req);
      const code = String(body.code || '').trim().toUpperCase();
      if (!isValidCode(code)) throw httpError(400, '6자리 종목 코드를 입력해 주세요.');
      if (store.stocks.some((s) => s.code === code)) throw httpError(409, '이미 추가된 종목입니다.');
      let name = body.name && String(body.name).trim();
      if (!name) {
        // 이름 없이 코드만 입력한 경우 실제 시세를 조회해 종목을 확인한다.
        try {
          name = (await quoteLookup(code)).name;
        } catch {
          throw httpError(404, '해당 종목을 찾을 수 없습니다.');
        }
      }
      store.addStock({ code, name });
      return { code, name };
    },
    'GET /api/search': async (req, url) => search(url.searchParams.get('q')),
    'GET /api/settings': async () => store.settings,
    'PUT /api/settings': async (req) => {
      try {
        return store.updateSettings(await readJson(req));
      } catch (err) {
        throw httpError(400, err.message);
      }
    },
    'GET /api/report': async () => store.data.lastReport,
    'POST /api/report/run': async () => runMorningReport(null),
    'GET /api/push/public-key': async () => ({ publicKey: pusher.publicKey }),
    'POST /api/push/subscribe': async (req) => {
      try {
        store.addSubscription(await readJson(req));
      } catch (err) {
        throw httpError(400, err.message);
      }
      return { ok: true };
    },
    'POST /api/push/unsubscribe': async (req) => {
      store.removeSubscription((await readJson(req)).endpoint);
      return { ok: true };
    },
  };

  async function handle(req, res) {
    const url = new URL(req.url, 'http://localhost');
    try {
      if (url.pathname.startsWith('/api/')) {
        const del = url.pathname.match(/^\/api\/stocks\/([0-9A-Za-z]{6})$/);
        let result;
        if (req.method === 'DELETE' && del) {
          if (!store.removeStock(del[1].toUpperCase())) throw httpError(404, '목록에 없는 종목입니다.');
          result = { ok: true };
        } else {
          const route = routes[`${req.method} ${url.pathname}`];
          if (!route) throw httpError(404, 'Not found');
          result = await route(req, url);
        }
        return sendJson(res, 200, result);
      }
      return serveStatic(url.pathname, res);
    } catch (err) {
      return sendJson(res, err.status || 500, { error: err.message || '서버 오류' });
    }
  }

  return { handle, runMorningReport };
}

function httpError(status, message) {
  const err = new Error(message);
  err.status = status;
  return err;
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > 64 * 1024) {
        reject(httpError(413, '요청이 너무 큽니다.'));
        req.destroy();
      } else chunks.push(c);
    });
    req.on('end', () => {
      try {
        resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {});
      } catch {
        reject(httpError(400, '잘못된 JSON 형식입니다.'));
      }
    });
    req.on('error', reject);
  });
}

function sendJson(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body ?? null));
}

function serveStatic(pathname, res) {
  const rel = pathname === '/' ? 'index.html' : decodeURIComponent(pathname).replace(/^\/+/, '');
  const file = path.resolve(PUBLIC_DIR, rel);
  if (!file.startsWith(PUBLIC_DIR + path.sep)) {
    res.writeHead(403);
    return res.end();
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('Not found');
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
}

if (require.main === module) {
  const store = new Store(path.join(DATA_DIR, 'store.json'));
  const pusher = createPusher({ dataDir: DATA_DIR, store });
  const app = createApp({ store, pusher });
  http.createServer(app.handle).listen(PORT, () => {
    console.log(`아침 주식 알리미 실행 중: http://localhost:${PORT}`);
    console.log(`알림 시각: 매일 ${store.settings.time} (KST)${store.settings.weekdaysOnly ? ', 평일만' : ''}`);
  });
  startScheduler({ store, run: (date) => app.runMorningReport(date) });
}

module.exports = { createApp };
