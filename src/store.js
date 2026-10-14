'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_STOCKS = [
  { code: '005930', name: '삼성전자' },
  { code: '000660', name: 'SK하이닉스' },
];

const DEFAULT_SETTINGS = {
  enabled: true,
  time: '08:30', // 한국 시간(KST) 기준
  weekdaysOnly: true,
};

function defaults() {
  return {
    stocks: DEFAULT_STOCKS.map((s) => ({ ...s })),
    settings: { ...DEFAULT_SETTINGS },
    subscriptions: [],
    lastReport: null,
    lastRunDate: null,
  };
}

// 단일 사용자용 JSON 파일 저장소
class Store {
  constructor(file) {
    this.file = file;
    this.data = this.load();
  }

  load() {
    try {
      const raw = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      const base = defaults();
      return { ...base, ...raw, settings: { ...base.settings, ...(raw.settings || {}) } };
    } catch {
      return defaults();
    }
  }

  save() {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.data, null, 2));
    fs.renameSync(tmp, this.file);
  }

  get stocks() {
    return this.data.stocks;
  }

  addStock(stock) {
    if (this.data.stocks.some((s) => s.code === stock.code)) return false;
    this.data.stocks.push({ code: stock.code, name: stock.name || stock.code });
    this.save();
    return true;
  }

  removeStock(code) {
    const before = this.data.stocks.length;
    this.data.stocks = this.data.stocks.filter((s) => s.code !== code);
    if (this.data.stocks.length === before) return false;
    this.save();
    return true;
  }

  get settings() {
    return this.data.settings;
  }

  updateSettings(patch) {
    const next = { ...this.data.settings };
    if (typeof patch.enabled === 'boolean') next.enabled = patch.enabled;
    if (typeof patch.weekdaysOnly === 'boolean') next.weekdaysOnly = patch.weekdaysOnly;
    if (patch.time !== undefined) {
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(patch.time)) throw new Error('시간은 HH:MM 형식이어야 합니다.');
      if (patch.time !== next.time) this.data.lastRunDate = null;
      next.time = patch.time;
    }
    this.data.settings = next;
    this.save();
    return next;
  }

  get subscriptions() {
    return this.data.subscriptions;
  }

  addSubscription(sub) {
    if (!sub || typeof sub.endpoint !== 'string') throw new Error('잘못된 구독 정보입니다.');
    this.data.subscriptions = this.data.subscriptions.filter((s) => s.endpoint !== sub.endpoint);
    this.data.subscriptions.push(sub);
    this.save();
  }

  removeSubscription(endpoint) {
    this.data.subscriptions = this.data.subscriptions.filter((s) => s.endpoint !== endpoint);
    this.save();
  }

  setReport(report, runDate) {
    this.data.lastReport = report;
    if (runDate) this.data.lastRunDate = runDate;
    this.save();
  }
}

module.exports = { Store, DEFAULT_STOCKS, DEFAULT_SETTINGS };
