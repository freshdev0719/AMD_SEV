'use strict';

const ARROW = { up: '▲', down: '▼', flat: '■' };

function formatPrice(n) {
  return Math.round(n).toLocaleString('ko-KR');
}

function formatRate(n) {
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

// 푸시 알림에 들어갈 짧은 요약 문구를 만든다.
function summarize(snapshot) {
  const ok = snapshot.quotes.filter((q) => !q.error);
  const up = ok.filter((q) => q.direction === 'up').length;
  const down = ok.filter((q) => q.direction === 'down').length;
  const lines = snapshot.quotes.map((q) => {
    if (q.error) return `${q.name || q.code}: 조회 실패`;
    return `${ARROW[q.direction]} ${q.name} ${formatPrice(q.price)}원 (${formatRate(q.changeRate)})`;
  });
  return {
    title: `오늘의 아침 시세 · 상승 ${up} / 하락 ${down}`,
    body: lines.join('\n'),
  };
}

module.exports = { summarize, formatPrice, formatRate };
