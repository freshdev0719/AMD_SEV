'use strict';

const fs = require('fs');
const path = require('path');
const webpush = require('web-push');

// VAPID 키는 환경 변수로 지정하거나, 없으면 최초 실행 시 생성해 data 폴더에 보관한다.
function loadVapidKeys(dataDir) {
  if (process.env.VAPID_PUBLIC_KEY && process.env.VAPID_PRIVATE_KEY) {
    return { publicKey: process.env.VAPID_PUBLIC_KEY, privateKey: process.env.VAPID_PRIVATE_KEY };
  }
  const file = path.join(dataDir, 'vapid.json');
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    const keys = webpush.generateVAPIDKeys();
    fs.mkdirSync(dataDir, { recursive: true });
    fs.writeFileSync(file, JSON.stringify(keys, null, 2), { mode: 0o600 });
    return keys;
  }
}

function createPusher({ dataDir, store, log = console }) {
  const keys = loadVapidKeys(dataDir);
  webpush.setVapidDetails(process.env.VAPID_SUBJECT || 'mailto:admin@localhost', keys.publicKey, keys.privateKey);

  async function sendAll(payload) {
    const subs = [...store.subscriptions];
    let sent = 0;
    await Promise.all(
      subs.map(async (sub) => {
        try {
          await webpush.sendNotification(sub, JSON.stringify(payload), { TTL: 3600 });
          sent += 1;
        } catch (err) {
          // 만료되었거나 해지된 구독은 정리한다.
          if (err.statusCode === 404 || err.statusCode === 410) {
            store.removeSubscription(sub.endpoint);
          } else {
            log.error('[push] 전송 실패:', err.statusCode || '', err.message);
          }
        }
      }),
    );
    return { sent, total: subs.length };
  }

  return { publicKey: keys.publicKey, sendAll };
}

module.exports = { createPusher };
