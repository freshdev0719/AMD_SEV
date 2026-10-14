'use strict';

// 한국 시간(KST, UTC+9, 서머타임 없음) 기준 시각 계산
function kstParts(date = new Date()) {
  const kst = new Date(date.getTime() + 9 * 3600 * 1000);
  const iso = kst.toISOString();
  return {
    date: iso.slice(0, 10),
    time: iso.slice(11, 16),
    weekday: kst.getUTCDay(), // 0 = 일요일
  };
}

function toMinutes(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

// 예정 시각에 서버가 잠시 꺼져 있었다면 이 시간 안에 켜졌을 때 늦게라도 보낸다.
const CATCH_UP_MINUTES = 180;

// 지금이 아침 알림을 보낼 때인지 판단한다.
function isDue(settings, lastRunDate, now = new Date()) {
  if (!settings.enabled) return false;
  const { date, time, weekday } = kstParts(now);
  if (settings.weekdaysOnly && (weekday === 0 || weekday === 6)) return false;
  if (lastRunDate === date) return false;
  const late = toMinutes(time) - toMinutes(settings.time);
  return late >= 0 && late <= CATCH_UP_MINUTES;
}

function startScheduler({ store, run, intervalMs = 30 * 1000, log = console }) {
  let running = false;
  const tick = async () => {
    if (running || !isDue(store.settings, store.data.lastRunDate)) return;
    running = true;
    try {
      await run(kstParts().date);
    } catch (err) {
      log.error('[scheduler] 아침 알림 실패:', err.message);
    } finally {
      running = false;
    }
  };
  const timer = setInterval(tick, intervalMs);
  timer.unref();
  tick();
  return () => clearInterval(timer);
}

module.exports = { kstParts, isDue, startScheduler };
