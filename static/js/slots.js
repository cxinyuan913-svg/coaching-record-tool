// 找空檔頁邏輯：選日期範圍／時段／場館／時長 → 找空檔 → 複製訊息給學生

let venues = [];
let venuesReady = null;

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

function setDefaultDates() {
  // 預設查明天起一週
  const from = new Date();
  from.setDate(from.getDate() + 1);
  const to = new Date(from);
  to.setDate(to.getDate() + 6);
  document.getElementById("f-date-from").value = toLocalDateString(from);
  document.getElementById("f-date-to").value = toLocalDateString(to);
}

// containerId：單次找空檔用 venue-checks，固定時段用 r-venue-checks
function renderVenueChecks(checkedIds, containerId = "venue-checks") {
  document.getElementById(containerId).innerHTML = venues
    .map(
      (v) => `<label><input type="checkbox" value="${v.id}" ${
        checkedIds.includes(v.id) ? "checked" : ""
      } />${escapeHtml(v.name)}</label>`
    )
    .join("");
}

async function renderAreaButtons(buttonsId = "area-buttons", checksId = "venue-checks") {
  const presets = await api.get("/api/slot-search/areas");
  const box = document.getElementById(buttonsId);
  box.innerHTML = Object.entries(presets)
    .filter(([, ids]) => ids.length > 0)
    .map(
      ([area, ids]) =>
        `<button type="button" class="secondary" data-ids="${ids.join(",")}">${escapeHtml(area)}場館</button>`
    )
    .join("");
  box.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => renderVenueChecks(btn.dataset.ids.split(",").map(Number), checksId))
  );
}

function selectedTimeRange() {
  const preset = document.querySelector('input[name="time-preset"]:checked').value;
  if (preset !== "custom") return preset.split("-");
  return [document.getElementById("f-time-from").value, document.getElementById("f-time-to").value];
}

async function searchSlots() {
  const status = document.getElementById("search-status");
  const venueIds = [...document.querySelectorAll("#venue-checks input:checked")].map((el) =>
    Number(el.value)
  );
  if (venueIds.length === 0) {
    status.textContent = "請至少勾選一個場館";
    return;
  }
  const [timeFrom, timeTo] = selectedTimeRange();
  const button = document.getElementById("btn-search");
  button.disabled = true;
  status.textContent = "查詢中…";
  try {
    const result = await api.post("/api/slot-search", {
      date_from: document.getElementById("f-date-from").value,
      date_to: document.getElementById("f-date-to").value,
      time_from: timeFrom,
      time_to: timeTo,
      venue_ids: venueIds,
      duration_minutes: Number(document.getElementById("f-duration").value),
    });
    renderResult(result);
    status.textContent = "";
  } catch (e) {
    status.textContent = `失敗：${e.message}`;
  } finally {
    button.disabled = false;
  }
}

function busyText(list) {
  return list.length
    ? `當天已有：${list.map((b) => `${hm(b.start)}-${hm(b.end)} ${escapeHtml(b.venue_name)}`).join("、")}`
    : "當天沒有其他課";
}

function durationText(startIso, endIso) {
  const minutes = (new Date(endIso) - new Date(startIso)) / 60000;
  return minutes % 60 === 0 ? `${minutes / 60} 小時` : `${(minutes / 60).toFixed(1)} 小時`;
}

function renderResult(result) {
  const rows = [];
  if (result.anchored_candidates.length) {
    rows.push(`<tr class="group-row"><td colspan="4">第一組：同館接課（緊接既有課程，交通最省）</td></tr>`);
    result.anchored_candidates.forEach((c) =>
      rows.push(`<tr>
        <td>${dayLabel(c.date)}</td>
        <td>${hm(c.start)}-${hm(c.end)}</td>
        <td>${escapeHtml(c.venue_name)}</td>
        <td class="hint">同館接課</td>
      </tr>`)
    );
  }
  if (result.open_blocks.length) {
    rows.push(`<tr class="group-row"><td colspan="4">第二組：大空檔（整點開始、至少 2 小時，已算車程）</td></tr>`);
    result.open_blocks.forEach((b) =>
      rows.push(`<tr>
        <td>${dayLabel(b.date)}</td>
        <td>${hm(b.start)}-${hm(b.end)}</td>
        <td>${b.venue_names.map(escapeHtml).join("、")}</td>
        <td class="hint">共 ${durationText(b.start, b.end)}；${busyText(b.other_busy)}</td>
      </tr>`)
    );
  }
  document.getElementById("candidate-list").innerHTML =
    rows.join("") || `<tr><td colspan="4" class="hint">沒有候選時段</td></tr>`;

  document.getElementById("msg-output").value = result.message;
  document.getElementById("copy-status").textContent = "";
  document.getElementById("result-block").hidden = false;
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
  setDefaultDates();
  populateDurationSelect("f-duration", 240);
  document.getElementById("f-duration").value = "60";
  document.querySelectorAll('input[name="time-preset"]').forEach((el) =>
    el.addEventListener("change", () => {
      document.getElementById("custom-time").hidden = el.value !== "custom" || !el.checked;
    })
  );

  // slots_recurring.js 也要用場館清單，等這個 Promise 就好，不用再抓一次
  venuesReady = api.get("/api/venues");
  venues = await venuesReady;
  renderVenueChecks(venues.map((v) => v.id));
  await renderAreaButtons();
  await loadTravelTimes();
  // 還沒填過任何車程時，預設展開車程表提醒要填
  if (!document.querySelector(".travel-input[value]:not([value=''])")) {
    document.getElementById("travel-details").open = true;
  }

  document.getElementById("btn-search").addEventListener("click", searchSlots);
  document.getElementById("btn-copy").addEventListener("click", copyMessage);
  document.getElementById("btn-save-travel").addEventListener("click", saveTravelTimes);
});
