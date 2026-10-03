// 固定時段排課分頁：每週同一天、同一時段、同一場館，連續 N 週
// 共用 slots.js 的 venues、venuesReady、escapeHtml、renderVenueChecks、renderAreaButtons

const WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"];

// API 回傳的日期是 YYYY-MM-DD，直接切字串，不經過 Date 物件避免時區偏移
function md(dateString) {
  const [, m, d] = dateString.split("-").map(Number);
  return `${m}/${d}`;
}

function switchTab(tabId) {
  document.querySelectorAll("#tab-bar .tab").forEach((btn) =>
    btn.classList.toggle("active", btn.dataset.tab === tabId)
  );
  document.getElementById("tab-single").hidden = tabId !== "tab-single";
  document.getElementById("tab-recurring").hidden = tabId !== "tab-recurring";
}

function recurringTimeRange() {
  const preset = document.querySelector('input[name="r-time-preset"]:checked').value;
  if (preset !== "custom") return preset.split("-");
  return [document.getElementById("r-time-from").value, document.getElementById("r-time-to").value];
}

async function searchRecurring() {
  const status = document.getElementById("r-status");
  const venueIds = [...document.querySelectorAll("#r-venue-checks input:checked")].map((el) =>
    Number(el.value)
  );
  if (venueIds.length === 0) {
    status.textContent = "請至少勾選一個場館";
    return;
  }
  const [timeFrom, timeTo] = recurringTimeRange();
  const button = document.getElementById("btn-recurring");
  button.disabled = true;
  status.textContent = "查詢中…";
  try {
    const result = await api.post("/api/slot-search/recurring", {
      weekday: Number(document.getElementById("r-weekday").value),
      date_from: document.getElementById("r-date-from").value,
      weeks: Number(document.getElementById("r-weeks").value),
      time_from: timeFrom,
      time_to: timeTo,
      venue_ids: venueIds,
      duration_minutes: Number(document.getElementById("r-duration").value),
    });
    renderRecurring(result);
    status.textContent = "";
  } catch (e) {
    status.textContent = `失敗：${e.message}`;
  } finally {
    button.disabled = false;
  }
}

function optionSummary(o, weeks) {
  const parts = [
    o.skipped.length === 0 ? `${weeks} 週全部可以` : `需順延 ${o.skipped.length} 週`,
    `同館接課 ${o.adjacent_weeks} 週`,
    `當天本來就在這館 ${o.same_venue_weeks} 週`,
  ];
  return parts.join("｜");
}

function renderRecurring(result) {
  const weekday = WEEKDAY_NAMES[Number(document.getElementById("r-weekday").value)];
  document.getElementById("r-result-title").textContent =
    `結果：${md(result.first_date)} 起每${weekday}，連續 ${result.weeks} 週`;
  const box = document.getElementById("r-options");
  if (result.options.length === 0) {
    box.innerHTML = `<div class="panel hint">找不到能排滿 ${result.weeks} 堂的固定時段（最多順延 2 週）。可以試試放寬時段、多勾幾個場館，或減少週數。</div>`;
  } else {
    box.innerHTML = result.options
      .map(
        (o, i) => `<div class="panel recurring-option">
          <div class="recurring-head">
            <strong>#${i + 1}　${weekday} ${o.start_time.slice(0, 5)}-${o.end_time.slice(0, 5)}　${escapeHtml(o.venue_name)}</strong>
            <span class="hint">${optionSummary(o, result.weeks)}</span>
          </div>
          <div>日期：${o.dates.map(md).join("、")}</div>
          ${o.skipped
            .map((s) => `<div class="hint">⚠ ${md(s.date)} 跳過：${escapeHtml(s.reason)}（只有你看得到）</div>`)
            .join("")}
          <div class="panel-actions">
            <button type="button" class="secondary" data-copy="${i}">複製給學生的訊息</button>
            <span class="hint" data-copy-status="${i}"></span>
          </div>
        </div>`
      )
      .join("");
    box.querySelectorAll("[data-copy]").forEach((btn) =>
      btn.addEventListener("click", () => copyRecurring(result.options[Number(btn.dataset.copy)].message, btn.dataset.copy))
    );
  }
  document.getElementById("r-result-block").hidden = false;
}

async function copyRecurring(text, index) {
  const status = document.querySelector(`[data-copy-status="${index}"]`);
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    // 非 HTTPS 環境 clipboard API 不能用，退回暫時 textarea 選取後複製
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  status.textContent = "已複製";
}

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll("#tab-bar .tab").forEach((btn) =>
    btn.addEventListener("click", () => switchTab(btn.dataset.tab))
  );

  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  document.getElementById("r-date-from").value = toLocalDateString(tomorrow);
  populateDurationSelect("r-duration", 240);
  document.getElementById("r-duration").value = "60";
  document.querySelectorAll('input[name="r-time-preset"]').forEach((el) =>
    el.addEventListener("change", () => {
      document.getElementById("r-custom-time").hidden = el.value !== "custom" || !el.checked;
    })
  );

  await venuesReady;
  renderVenueChecks(venues.map((v) => v.id), "r-venue-checks");
  await renderAreaButtons("r-area-buttons", "r-venue-checks");
  document.getElementById("btn-recurring").addEventListener("click", searchRecurring);
});
