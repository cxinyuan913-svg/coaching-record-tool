// 找空檔頁邏輯：貼訊息 → 解析（Phase 1）→ 找空檔（Phase 2）→ 複製訊息

let venues = [];
let currentRequestId = null;

const STATUS_LABELS = {
  ok: "解析完成",
  needs_review: "需要人工確認",
  not_booking: "不是約課訊息",
};

const DURATION_SOURCE_LABELS = {
  request: "手動指定",
  message: "學生訊息有講",
  student_last_lesson: "依該學生最近一堂課",
  default: "預設值",
};

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// API 回傳的時間是沒有時區的台灣當地時間字串（例如 2026-10-06T19:00:00），
// 直接切字串顯示，不經過 Date 物件，避免瀏覽器時區換算造成偏移
function hm(isoString) {
  return isoString.slice(11, 16);
}

function dayLabel(dateString) {
  const [y, m, d] = dateString.split("-").map(Number);
  const weekday = WEEKDAYS[new Date(y, m - 1, d).getDay()];
  return `${m}/${d}(${weekday})`;
}

async function parseAndSuggest() {
  const text = document.getElementById("msg-input").value.trim();
  if (!text) return;
  const status = document.getElementById("parse-status");
  const button = document.getElementById("btn-parse");
  button.disabled = true;
  status.textContent = "解析中…";
  document.getElementById("result-block").hidden = true;
  document.getElementById("conditions-block").hidden = true;
  try {
    const parsed = await api.post("/api/booking-requests/parse", { text });
    currentRequestId = parsed.booking_request_id;
    renderParseSummary(parsed);
    status.textContent = "";
    if (parsed.resolved_windows.length === 0) {
      status.textContent = "這則訊息沒有可用的日期時段，無法找空檔";
      return;
    }
    await suggest(null);
  } catch (e) {
    status.textContent = `失敗：${e.message}`;
  } finally {
    button.disabled = false;
  }
}

function renderParseSummary(parsed) {
  const box = document.getElementById("parse-summary");
  const p = parsed.parsed || {};
  const windows = parsed.resolved_windows
    .map((w) => `${dayLabel(w.date)} ${hm(w.start)}-${hm(w.end)}`)
    .join("、");
  let studentText = p.student_name ? escapeHtml(p.student_name) : "（沒提到）";
  if (parsed.student_match && parsed.student_match.needs_review) studentText += "　⚠ 沒有確定比對到";
  let areaText = p.area ? escapeHtml(p.area) : "（沒提到，找全部場館）";
  if (parsed.area_match && parsed.area_match.needs_review) areaText += "　⚠ 沒有對到場館";

  box.innerHTML = `
    <div><strong>${STATUS_LABELS[parsed.status] || parsed.status}</strong>
      <span class="hint">（紀錄編號 ${parsed.booking_request_id}）</span></div>
    <div>學生：${studentText}</div>
    <div>地區：${areaText}</div>
    <div>時段：${windows || "（無）"}</div>
    <div>時長：${p.duration_minutes ? `${p.duration_minutes} 分鐘` : "（沒提到）"}</div>
    ${parsed.ambiguities.map((a) => `<div class="hint">⚠ ${escapeHtml(a)}</div>`).join("")}
  `;
  box.hidden = false;
}

async function suggest(overrides) {
  const result = await api.post(`/api/booking-requests/${currentRequestId}/suggest`, overrides);
  renderConditions(result);
  renderResult(result);
}

function renderConditions(result) {
  const select = document.getElementById("f-duration");
  // 時長不是半小時的倍數（例如學生說 45 分鐘）時，選單裡沒有這個值，補一個
  if (![...select.options].some((o) => o.value === String(result.duration_minutes))) {
    const opt = document.createElement("option");
    opt.value = result.duration_minutes;
    opt.textContent = `${result.duration_minutes} 分鐘`;
    select.appendChild(opt);
  }
  select.value = String(result.duration_minutes);
  document.getElementById("duration-source").textContent =
    `（${DURATION_SOURCE_LABELS[result.duration_source] || result.duration_source}）`;
  const box = document.getElementById("venue-checks");
  box.innerHTML = venues
    .map(
      (v) => `<label><input type="checkbox" value="${v.id}" ${
        result.venue_ids.includes(v.id) ? "checked" : ""
      } />${escapeHtml(v.name)}</label>`
    )
    .join("");
  document.getElementById("conditions-block").hidden = false;
}

function renderResult(result) {
  document.getElementById("notes").innerHTML = result.notes
    .map((n) => `<div>${escapeHtml(n)}</div>`)
    .join("");

  const rows = result.anchored_candidates.map(
    (c) => `<tr>
      <td>${dayLabel(c.date)}</td>
      <td>${hm(c.start)}-${hm(c.end)}</td>
      <td>${escapeHtml(c.venue_name)}</td>
      <td>${c.cross_venue ? "跨館貼靠" : "同館貼靠"}</td>
    </tr>`
  );
  result.dedicated_dates.forEach((d) => {
    const others = d.other_busy.length
      ? `當天已有：${d.other_busy
          .map((b) => `${hm(b.start)}-${hm(b.end)} ${escapeHtml(b.venue_name)}`)
          .join("、")}`
      : "當天沒有其他課";
    rows.push(`<tr>
      <td>${dayLabel(d.date)}</td>
      <td class="hint">${others}</td>
      <td>—</td>
      <td>專程</td>
    </tr>`);
  });
  document.getElementById("candidate-list").innerHTML =
    rows.join("") || `<tr><td colspan="4" class="hint">沒有候選時段</td></tr>`;

  document.getElementById("msg-output").value = result.message;
  document.getElementById("copy-status").textContent = "";
  document.getElementById("result-block").hidden = false;
}

async function resuggest() {
  const venueIds = [...document.querySelectorAll("#venue-checks input:checked")].map((el) =>
    Number(el.value)
  );
  if (venueIds.length === 0) {
    document.getElementById("notes").innerHTML = "<div>請至少勾選一個場館</div>";
    return;
  }
  try {
    await suggest({
      duration_minutes: Number(document.getElementById("f-duration").value),
      venue_ids: venueIds,
    });
  } catch (e) {
    document.getElementById("notes").innerHTML = `<div>失敗：${escapeHtml(e.message)}</div>`;
  }
}

async function copyMessage() {
  const textarea = document.getElementById("msg-output");
  const status = document.getElementById("copy-status");
  try {
    await navigator.clipboard.writeText(textarea.value);
  } catch (e) {
    // 非 HTTPS 環境 clipboard API 不能用，退回選取後複製
    textarea.select();
    document.execCommand("copy");
  }
  status.textContent = "已複製";
}

// ---- 車程表 ----

async function loadTravelTimes() {
  const rows = await api.get("/api/venue-travel-times");
  const minutes = new Map(rows.map((r) => [`${r.venue_a_id}-${r.venue_b_id}`, r.travel_minutes]));
  const sorted = [...venues].sort((a, b) => a.id - b.id);
  const html = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      const a = sorted[i];
      const b = sorted[j];
      const value = minutes.get(`${a.id}-${b.id}`);
      html.push(`<tr>
        <td>${escapeHtml(a.name)}</td>
        <td>${escapeHtml(b.name)}</td>
        <td><input type="number" min="0" max="300" class="travel-input"
          data-a="${a.id}" data-b="${b.id}" value="${value ?? ""}" /></td>
      </tr>`);
    }
  }
  document.getElementById("travel-list").innerHTML =
    html.join("") || `<tr><td colspan="3" class="hint">至少要有兩個場館</td></tr>`;
}

async function saveTravelTimes() {
  const status = document.getElementById("travel-status");
  const items = [...document.querySelectorAll(".travel-input")].map((el) => ({
    venue_a_id: Number(el.dataset.a),
    venue_b_id: Number(el.dataset.b),
    // 空白代表沒設定，送 null 讓後端刪除這組
    travel_minutes: el.value === "" ? null : Number(el.value),
  }));
  try {
    await api.put("/api/venue-travel-times", items);
    status.textContent = "已儲存";
    await loadTravelTimes();
  } catch (e) {
    status.textContent = `失敗：${e.message}`;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  populateDurationSelect("f-duration", 240);
  venues = await api.get("/api/venues");
  await loadTravelTimes();
  // 還沒填過任何車程時，預設展開車程表提醒要填
  if (!document.querySelector(".travel-input[value]:not([value=''])")) {
    document.getElementById("travel-details").open = true;
  }

  document.getElementById("btn-parse").addEventListener("click", parseAndSuggest);
  document.getElementById("btn-suggest").addEventListener("click", resuggest);
  document.getElementById("btn-copy").addEventListener("click", copyMessage);
  document.getElementById("btn-save-travel").addEventListener("click", saveTravelTimes);
});
