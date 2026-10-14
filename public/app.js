'use strict';

const $ = (sel) => document.querySelector(sel);
const ARROW = { up: '▲', down: '▼', flat: '■' };
const TREND_LABEL = { up: '상승세', down: '하락세', flat: '보합세' };
const REFRESH_MS = 60 * 1000;

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.error) || `요청 실패 (${res.status})`);
  return data;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) if (child) node.append(child);
  return node;
}

const fmtPrice = (n) => Math.round(n).toLocaleString('ko-KR');
const fmtRate = (n) => (n > 0 ? '+' : '') + n.toFixed(2) + '%';
const fmtTime = (iso) => new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });

function sparkline(history, direction) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 84 24');
  svg.setAttribute('class', `spark ${direction}`);
  svg.setAttribute('aria-hidden', 'true');
  const closes = history.map((h) => h.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const points = closes
    .map((c, i) => `${(i / (closes.length - 1)) * 82 + 1},${22 - ((c - min) / span) * 20}`)
    .join(' ');
  const line = document.createElementNS(ns, 'polyline');
  line.setAttribute('points', points);
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke-width', '2');
  line.setAttribute('stroke-linejoin', 'round');
  line.setAttribute('stroke-linecap', 'round');
  svg.append(line);
  return svg;
}

function renderCard(q) {
  const removeBtn = el('button', { class: 'remove', type: 'button', 'aria-label': `${q.name} 삭제`, title: '삭제', text: '✕' });
  removeBtn.addEventListener('click', () => removeStock(q.code, q.name));

  if (q.error) {
    return el('li', { class: 'card flat' }, [
      el('div', {}, [el('div', { class: 'name', text: q.name || q.code }), el('div', { class: 'meta', text: q.code })]),
      el('div', { class: 'right error', text: '시세를 불러오지 못했습니다' }),
      removeBtn,
    ]);
  }

  const trend = q.trend && q.history && q.history.length >= 2
    ? el('div', { class: 'trend' }, [
      el('span', { class: `pill ${q.trend.direction}`, text: `${q.trend.days}일 ${TREND_LABEL[q.trend.direction]} ${fmtRate(q.trend.rate)}` }),
      sparkline(q.history, q.trend.direction),
    ])
    : el('div', { class: 'trend' }, [el('span', { class: `pill ${q.direction}`, text: `전일 대비 ${TREND_LABEL[q.direction]}` })]);

  return el('li', { class: `card ${q.direction}` }, [
    el('div', {}, [
      el('div', { class: 'name', text: q.name }),
      el('div', { class: 'meta', text: [q.code, q.market, q.marketStatus === 'OPEN' ? '장중' : q.marketStatus === 'CLOSE' ? '장마감' : ''].filter(Boolean).join(' · ') }),
    ]),
    el('div', { class: 'right price', text: `${fmtPrice(q.price)}원` }),
    trend,
    el('div', { class: 'right change', text: `${ARROW[q.direction]} ${fmtPrice(Math.abs(q.change))} (${fmtRate(q.changeRate)})` }),
    removeBtn,
  ]);
}

async function loadQuotes(force = false) {
  const btn = $('#refresh');
  btn.disabled = true;
  try {
    const data = await api(`/api/quotes${force ? '?refresh=1' : ''}`);
    const cards = $('#cards');
    cards.replaceChildren(...data.quotes.map(renderCard));
    if (!data.quotes.length) cards.append(el('li', { class: 'empty', text: '관심 종목을 추가해 주세요.' }));
    $('#updated').textContent = `${fmtTime(data.fetchedAt)} 기준`;
  } catch (err) {
    $('#updated').textContent = `시세 조회 실패: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function loadReport() {
  const report = await api('/api/report').catch(() => null);
  if (!report) return;
  $('#report').hidden = false;
  $('#report-title').textContent = report.title;
  $('#report-time').textContent = fmtTime(report.fetchedAt);
}

async function removeStock(code, name) {
  if (!confirm(`${name} 종목을 관심 목록에서 삭제할까요?`)) return;
  try {
    await api(`/api/stocks/${code}`, { method: 'DELETE' });
    await loadQuotes(true);
  } catch (err) {
    alert(err.message);
  }
}

// ---- 종목 검색 / 추가 ----
let suggestions = [];
let activeIndex = -1;
let searchTimer;

function showMessage(target, text, isError = false) {
  target.textContent = text;
  target.classList.toggle('err', isError);
}

function renderSuggestions() {
  const list = $('#suggest');
  list.replaceChildren(
    ...suggestions.map((s, i) => {
      const li = el('li', { class: i === activeIndex ? 'active' : '' }, [
        el('span', { text: s.name }),
        el('span', { class: 'muted', text: `${s.code} ${s.market}` }),
      ]);
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        addStock(s);
      });
      return li;
    }),
  );
  list.hidden = suggestions.length === 0;
}

function hideSuggestions() {
  suggestions = [];
  activeIndex = -1;
  renderSuggestions();
}

async function addStock(stock) {
  const msg = $('#add-msg');
  hideSuggestions();
  try {
    const added = await api('/api/stocks', { method: 'POST', body: JSON.stringify(stock) });
    $('#search').value = '';
    showMessage(msg, `${added.name}(${added.code}) 종목을 추가했습니다.`);
    await loadQuotes(true);
  } catch (err) {
    showMessage(msg, err.message, true);
  }
}

$('#search').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (!q || /^\d{1,6}$/.test(q)) return hideSuggestions();
  searchTimer = setTimeout(async () => {
    try {
      suggestions = await api(`/api/search?q=${encodeURIComponent(q)}`);
    } catch {
      suggestions = [];
    }
    activeIndex = suggestions.length ? 0 : -1;
    renderSuggestions();
  }, 250);
});

$('#search').addEventListener('keydown', (e) => {
  if (!suggestions.length) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const step = e.key === 'ArrowDown' ? 1 : -1;
    activeIndex = (activeIndex + step + suggestions.length) % suggestions.length;
    renderSuggestions();
  } else if (e.key === 'Escape') {
    hideSuggestions();
  }
});

$('#search').addEventListener('blur', () => setTimeout(hideSuggestions, 100));

$('#add-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('#search').value.trim();
  if (suggestions[activeIndex]) return addStock(suggestions[activeIndex]);
  if (/^[0-9A-Za-z]{6}$/.test(q)) return addStock({ code: q });
  showMessage($('#add-msg'), '목록에서 종목을 선택하거나 6자리 종목 코드를 입력해 주세요.', true);
});

// ---- 알림 설정 ----
async function loadSettings() {
  const s = await api('/api/settings');
  $('#enabled').checked = s.enabled;
  $('#time').value = s.time;
  $('#weekdays').checked = s.weekdaysOnly;
}

$('#settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const s = await api('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ enabled: $('#enabled').checked, time: $('#time').value, weekdaysOnly: $('#weekdays').checked }),
    });
    showMessage($('#settings-msg'), s.enabled
      ? `저장했습니다. ${s.weekdaysOnly ? '평일' : '매일'} ${s.time}에 알려드릴게요.`
      : '저장했습니다. 아침 알림이 꺼져 있습니다.');
  } catch (err) {
    showMessage($('#settings-msg'), err.message, true);
  }
});

$('#run-now').addEventListener('click', async () => {
  const msg = $('#settings-msg');
  try {
    const { push } = await api('/api/report/run', { method: 'POST' });
    await Promise.all([loadReport(), loadQuotes()]);
    showMessage(msg, push.total
      ? `리포트를 ${push.sent}/${push.total}개 기기로 보냈습니다.`
      : '리포트를 만들었습니다. 알림을 받으려면 "이 기기에서 알림 받기"를 눌러 주세요.');
  } catch (err) {
    showMessage(msg, err.message, true);
  }
});

// ---- 웹 푸시 ----
function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

async function currentSubscription() {
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

async function updatePushButton() {
  const btn = $('#push-btn');
  if (!pushSupported) {
    btn.disabled = true;
    btn.textContent = '이 브라우저는 알림을 지원하지 않습니다';
    return;
  }
  const sub = await currentSubscription();
  btn.textContent = sub ? '이 기기 알림 끄기' : '이 기기에서 알림 받기';
}

$('#push-btn').addEventListener('click', async () => {
  const msg = $('#settings-msg');
  try {
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      await api('/api/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: existing.endpoint }) });
      await existing.unsubscribe();
      showMessage(msg, '이 기기의 알림을 껐습니다.');
    } else {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') throw new Error('브라우저 알림 권한이 허용되지 않았습니다.');
      const { publicKey } = await api('/api/push/public-key');
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
      await api('/api/push/subscribe', { method: 'POST', body: JSON.stringify(sub) });
      showMessage(msg, '이 기기에서 아침 알림을 받습니다.');
    }
  } catch (err) {
    showMessage(msg, err.message, true);
  }
  updatePushButton();
});

// ---- 시작 ----
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').then(updatePushButton).catch(() => {});
else updatePushButton();

loadQuotes();
loadReport();
loadSettings().catch((err) => showMessage($('#settings-msg'), err.message, true));
setInterval(() => {
  if (document.visibilityState === 'visible') loadQuotes();
}, REFRESH_MS);
