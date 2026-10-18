"use strict";

const $ = (sel) => document.querySelector(sel);
const PYEONG = 3.3058;
const STORE_KEY = "landfinder.form.v1";

const state = {
  results: [],
  sort: { key: "matched_count", asc: false },
  selected: null,
  jobId: null,
  lastCriteria: null,
};

// MARK: - 공통

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtPrice(manwon) {
  if (manwon == null) return "-";
  const eok = Math.floor(manwon / 10000);
  const rest = manwon % 10000;
  if (eok === 0) return `${rest.toLocaleString()}만`;
  return rest === 0 ? `${eok}억` : `${eok}억 ${rest.toLocaleString()}`;
}

function fmtGap(gap) {
  if (gap == null) return '<span class="muted">-</span>';
  const pct = (gap * 100).toFixed(1);
  const cls = gap > 0.005 ? "up" : gap < -0.005 ? "down" : "";
  return `<span class="${cls}">${gap > 0 ? "+" : ""}${pct}%</span>`;
}

function fmtDate(iso) {
  return iso ? iso.slice(2).replaceAll("-", ".") : "-";
}

function fmtArea(exclusive, supply) {
  if (exclusive == null) return "-";
  const py = supply ? `${Math.round(supply / PYEONG)}평` : `${(exclusive / PYEONG).toFixed(1)}평`;
  return `${exclusive.toFixed(1)}㎡ <span class="sub">/ ${py}</span>`;
}

function shortAddress(address) {
  const parts = (address || "").split(" ");
  return parts.slice(-1)[0] || "";
}

// MARK: - 지역 선택

async function fillSelect(select, cortarNo, placeholder) {
  select.innerHTML = `<option value="">${placeholder}</option>`;
  select.disabled = true;
  const regions = await api(`/api/regions?cortarNo=${cortarNo}`);
  for (const r of regions) {
    select.insertAdjacentHTML("beforeend", `<option value="${esc(r.cortar_no)}">${esc(r.name)}</option>`);
  }
  select.disabled = false;
  return regions;
}

async function loadDongs(cortarNo, checked = []) {
  const box = $("#dongs");
  if (!cortarNo) {
    box.innerHTML = '<p class="muted">시·군·구를 고르세요.</p>';
    return;
  }
  box.innerHTML = '<p class="muted">불러오는 중…</p>';
  const regions = await api(`/api/regions?cortarNo=${cortarNo}`);
  box.innerHTML = regions
    .map((r) => `<label class="check"><input type="checkbox" value="${esc(r.cortar_no)}" ${checked.includes(r.cortar_no) ? "checked" : ""}> ${esc(r.name)}</label>`)
    .join("") || '<p class="muted">동 목록이 없습니다.</p>';
}

function checkedDongs() {
  return [...document.querySelectorAll("#dongs input:checked")].map((i) => i.value);
}

// MARK: - 조건

function numberOrNull(value, scale = 1) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n * scale * 100) / 100 : null;
}

function readCriteria() {
  const f = $("#criteria").elements;
  const priceMin = numberOrNull(f.price_min.value, 10000);
  const priceMax = numberOrNull(f.price_max.value, 10000);
  return {
    cortar_nos: checkedDongs(),
    price_min: priceMin == null ? null : Math.round(priceMin),
    price_max: priceMax == null ? null : Math.round(priceMax),
    area_min: numberOrNull(f.area_min.value),
    area_max: numberOrNull(f.area_max.value),
    households_min: numberOrNull(f.households_min.value),
    build_year_min: numberOrNull(f.build_year_min.value),
    build_year_max: numberOrNull(f.build_year_max.value),
    exclude_low_floor: f.exclude_low_floor.checked,
    south_only: f.south_only.checked,
    confirmed_within_days: numberOrNull(f.confirmed_within_days.value),
    max_gap: numberOrNull(f.max_gap.value),
    real_months: numberOrNull(f.real_months.value) || 12,
  };
}

function saveForm() {
  const f = $("#criteria").elements;
  const data = { sido: $("#sido").value, sigungu: $("#sigungu").value, dongs: checkedDongs(), fields: {} };
  for (const el of f) {
    if (!el.name) continue;
    data.fields[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  try { localStorage.setItem(STORE_KEY, JSON.stringify(data)); } catch (e) { /* 저장 못 해도 동작에는 지장 없음 */ }
}

async function restoreForm() {
  let data = null;
  try { data = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch (e) { data = null; }
  await fillSelect($("#sido"), "0000000000", "선택");
  if (!data) return;
  const f = $("#criteria").elements;
  for (const [name, value] of Object.entries(data.fields || {})) {
    const el = f[name];
    if (!el) continue;
    if (el.type === "checkbox") el.checked = !!value; else el.value = value;
  }
  updateAreaHint();
  if (data.sido) {
    $("#sido").value = data.sido;
    await fillSelect($("#sigungu"), data.sido, "선택");
    if (data.sigungu) {
      $("#sigungu").value = data.sigungu;
      await loadDongs(data.sigungu, data.dongs || []);
    }
  }
}

function updateAreaHint() {
  const f = $("#criteria").elements;
  const lo = numberOrNull(f.area_min.value);
  const hi = numberOrNull(f.area_max.value);
  const toPy = (a) => (a / PYEONG).toFixed(1);
  $("#area-hint").textContent = lo || hi ? `전용 ${lo ? toPy(lo) : "0"}평 ~ ${hi ? toPy(hi) : "∞"}평 (흔히 59㎡≈25평형, 84㎡≈34평형)` : "흔히 59㎡≈25평형, 84㎡≈34평형";
}

// MARK: - 검색

function setSearching(on) {
  $("#search-btn").disabled = on;
  $("#search-btn").textContent = on ? "찾는 중…" : "단지 찾기";
  $("#cancel-btn").hidden = !on;
  $("#progress").hidden = !on;
}

function showWarnings(list, isError = false) {
  $("#warnings").innerHTML = (list || []).map((w) => `<p class="${isError ? "error" : ""}">${esc(w)}</p>`).join("");
}

async function startSearch(event) {
  event.preventDefault();
  const criteria = readCriteria();
  if (!criteria.cortar_nos.length) {
    showWarnings(["읍·면·동을 하나 이상 선택하세요."], true);
    return;
  }
  saveForm();
  state.lastCriteria = criteria;
  showWarnings([]);
  setSearching(true);
  try {
    const { job_id } = await api("/api/search", { method: "POST", body: criteria });
    state.jobId = job_id;
    await pollSearch(job_id);
  } catch (e) {
    showWarnings([e.message], true);
  } finally {
    setSearching(false);
    state.jobId = null;
  }
}

async function pollSearch(jobId) {
  for (;;) {
    const job = await api(`/api/search/${jobId}`);
    const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
    $("#progress-fill").style.width = `${pct}%`;
    $("#progress-text").textContent = `${job.message} (${job.done}/${job.total})`;
    if (job.status === "done") {
      state.results = job.results.map(toRow);
      renderResults();
      showWarnings(job.warnings);
      return;
    }
    if (job.status === "error") throw new Error(job.error);
    await new Promise((r) => setTimeout(r, 400));
  }
}

function toRow(result) {
  const c = result.complex;
  const bucket = result.min_price_area != null ? Math.round(result.min_price_area) : null;
  const real = (result.real || []).find((r) => r.bucket === bucket);
  return {
    result,
    complex_no: c.complex_no,
    name: c.name,
    address: shortAddress(c.address),
    households: c.households,
    build_year: c.build_year,
    matched_count: result.matched_count,
    total_listings: result.total_listings,
    min_price: result.min_price,
    min_price_area: result.min_price_area,
    real_median: real ? real.median : null,
    min_gap: result.min_gap,
  };
}

function renderResults() {
  const { key, asc } = state.sort;
  const rows = [...state.results].sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    const cmp = typeof x === "string" ? x.localeCompare(y, "ko") : x - y;
    return asc ? cmp : -cmp;
  });
  document.querySelectorAll("#results th[data-key]").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.key === key);
    th.classList.toggle("asc", th.dataset.key === key && asc);
  });
  $("#results tbody").innerHTML = rows
    .map((r) => `
      <tr data-no="${esc(r.complex_no)}" class="${state.selected === r.complex_no ? "active" : ""}">
        <td class="name">${esc(r.name)}</td>
        <td>${esc(r.address)}</td>
        <td class="num">${r.households != null ? r.households.toLocaleString() : "-"}</td>
        <td class="num">${r.build_year ?? "-"}</td>
        <td class="num">${r.matched_count} <span class="sub">/ ${r.total_listings}</span></td>
        <td class="num">${fmtPrice(r.min_price)} <span class="sub">${r.min_price_area ? Math.round(r.min_price_area) + "㎡" : ""}</span></td>
        <td class="num">${fmtPrice(r.real_median)}</td>
        <td class="num">${fmtGap(r.min_gap)}</td>
      </tr>`)
    .join("");
  $("#results-empty").hidden = rows.length > 0;
  if (!rows.length) $("#results-empty").textContent = "조건에 맞는 단지가 없습니다. 조건을 넓혀 보세요.";
  $("#results-title").textContent = `단지 ${rows.length}곳`;
  $("#results-meta").textContent = rows.length ? "실거래 중위가 = 최저 호가 매물과 같은 면적 · 최저 괴리율 = 조건 매물 중 같은 면적 실거래 대비 가장 싼 매물의 비율" : "";
}

// MARK: - 단지 매물

async function showDetail(complexNo) {
  const row = state.results.find((r) => r.complex_no === complexNo);
  if (!row) return;
  state.selected = complexNo;
  renderResults();
  const detail = $("#detail");
  detail.hidden = false;
  $("#detail-title").textContent = row.name;
  $("#detail-meta").textContent = "매물을 불러오는 중…";
  $("#listings tbody").innerHTML = "";
  $("#real-summary").innerHTML = "";
  try {
    const showAll = $("#show-all").checked ? "1" : "0";
    const data = await api(`/api/complexes/${complexNo}/listings?all=${showAll}`, {
      method: "POST",
      body: state.lastCriteria || readCriteria(),
    });
    if (state.selected !== complexNo) return; // 그 사이 다른 단지를 눌렀으면 버림
    renderDetail(row, data);
  } catch (e) {
    $("#detail-meta").textContent = `불러오지 못했습니다: ${e.message}`;
  }
}

function renderDetail(row, data) {
  const c = row.result.complex;
  $("#detail-meta").textContent = [
    c.address,
    c.households ? `${c.households.toLocaleString()}세대` : null,
    c.build_year ? `${c.build_year}년` : null,
    `매물 ${data.listings.length}건 / 전체 ${data.total_listings}건`,
  ].filter(Boolean).join(" · ");

  const link = $("#detail-link");
  link.hidden = !data.url;
  if (data.url) link.href = data.url;

  $("#real-summary").innerHTML = data.real
    .map((r) => {
      const latest = r.latest ? `최근 ${fmtDate(r.latest.deal_date)} ${fmtPrice(r.latest.price)}${r.latest.floor ? ` (${r.latest.floor}층)` : ""}` : "실거래 없음";
      return `<div class="chip">전용 ${r.bucket}㎡ · 실거래 중위 <b>${fmtPrice(r.median)}</b> <span class="sub">(${r.count}건)</span><br><span class="sub">${latest}</span></div>`;
    })
    .join("");

  $("#listings tbody").innerHTML = data.listings
    .map((l) => `
      <tr>
        <td>${esc(l.building || "-")} <span class="sub">${esc(l.floor_text)}</span></td>
        <td class="num">${fmtArea(l.exclusive_area, l.supply_area)}</td>
        <td>${esc(l.area_name)}</td>
        <td>${esc(l.direction)}</td>
        <td class="num"><b>${fmtPrice(l.price)}</b></td>
        <td class="num">${fmtGap(l.gap)}</td>
        <td>${fmtDate(l.confirmed)}</td>
        <td class="desc">${esc(l.description)}${(l.tags || []).slice(0, 3).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</td>
        <td class="sub">${esc(l.realtor)}${l.same_address_count > 1 ? ` 외 ${l.same_address_count - 1}곳` : ""}</td>
        <td>${l.url ? `<a class="link" href="${esc(l.url)}" target="_blank" rel="noopener">보기 ↗</a>` : ""}</td>
      </tr>`)
    .join("");
  $("#listings-empty").hidden = data.listings.length > 0;
}

// MARK: - 설정

async function openSettings() {
  const s = await api("/api/settings");
  const f = $("#settings-form").elements;
  f.token.value = s.token;
  f.cookie.value = s.cookie;
  f.min_interval.value = s.min_interval;
  $("#settings").showModal();
}

async function saveSettings() {
  const f = $("#settings-form").elements;
  await api("/api/settings", {
    method: "PUT",
    body: { token: f.token.value, cookie: f.cookie.value, min_interval: Number(f.min_interval.value) || 1 },
  });
  $("#settings").close();
}

// MARK: - 시작

async function init() {
  try {
    const status = await api("/api/status");
    const badge = $("#source-badge");
    badge.textContent = status.source === "demo" ? "데모 데이터" : "네이버 부동산";
    badge.classList.toggle("demo", status.source === "demo");
  } catch (e) { /* 배지는 없어도 됨 */ }

  $("#sido").addEventListener("change", async (e) => {
    await loadDongs("");
    if (e.target.value) await fillSelect($("#sigungu"), e.target.value, "선택");
    else { $("#sigungu").innerHTML = ""; $("#sigungu").disabled = true; }
  });
  $("#sigungu").addEventListener("change", (e) => loadDongs(e.target.value).catch((err) => showWarnings([err.message], true)));
  $("#dong-all").addEventListener("click", () => {
    const boxes = [...document.querySelectorAll("#dongs input")];
    const allOn = boxes.every((b) => b.checked);
    boxes.forEach((b) => { b.checked = !allOn; });
  });
  $("#criteria").addEventListener("submit", startSearch);
  $("#criteria").elements.area_min.addEventListener("input", updateAreaHint);
  $("#criteria").elements.area_max.addEventListener("input", updateAreaHint);
  $("#cancel-btn").addEventListener("click", () => {
    if (state.jobId) api(`/api/search/${state.jobId}`, { method: "DELETE" }).catch(() => {});
  });
  document.querySelectorAll("#results th[data-key]").forEach((th) =>
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      state.sort = { key, asc: state.sort.key === key ? !state.sort.asc : ["name", "address"].includes(key) };
      renderResults();
    }));
  $("#results tbody").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-no]");
    if (tr) showDetail(tr.dataset.no);
  });
  $("#show-all").addEventListener("change", () => state.selected && showDetail(state.selected));
  $("#settings-btn").addEventListener("click", () => openSettings().catch((e) => showWarnings([e.message], true)));
  $("#save-settings").addEventListener("click", () => saveSettings().catch((e) => alert(e.message)));
  $("#clear-cache").addEventListener("click", async () => {
    await api("/api/cache/clear", { method: "POST" });
    $("#clear-cache").textContent = "비웠습니다";
  });

  updateAreaHint();
  try {
    await restoreForm();
  } catch (e) {
    showWarnings([`지역 목록을 불러오지 못했습니다: ${e.message}`], true);
  }
}

init();
