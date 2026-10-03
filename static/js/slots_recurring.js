// 固定時段排課分頁：每週同一天，連續 N 週
// - 不指定希望時段：自動推薦前 10 名（POST /api/slot-search/recurring）
// - 指定希望時段：逐週排排看，撞課時選同館替代時段、可接課時提醒（POST .../recurring/plan）
// 共用 slots.js 的 venues、venuesReady、escapeHtml、renderVenueChecks、renderAreaButtons，
// 以及 common.js 的 chineseNumber（跟課程套組頁的學生訊息同一個格式）

const WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"];
const WEEKDAY_SHORT = "日一二三四五六"; // 對應 JS getDay()，週日=0

let currentPlan = null; // 逐週排排看的 API 結果
let lastSearch = null; // 最近一次查詢的條件（星期、時長），建立套組時用
let pendingPackage = null; // 準備建立套組的內容：{venueId, venueName, lessons}
let planChoices = []; // 每週的選擇：{kind: "pref" | "suggest" | "alt" | "skip", alt: 索引}

// API 回傳的日期是 YYYY-MM-DD，直接切字串，不經過 Date 物件換算避免時區偏移
function md(dateString) {
  const [, m, d] = dateString.split("-").map(Number);
  return `${m}/${d}`;
}

function mdWithWeekday(dateString) {
  const [y, m, d] = dateString.split("-").map(Number);
  return `${m}/${d}（${WEEKDAY_SHORT[new Date(y, m - 1, d).getDay()]}）`;
}

function hhmm(timeString) {
  return timeString.slice(0, 5);
}

// 跟課程套組頁「課程訊息」同一個格式，學生還沒付款所以不放付費日期跟匯款資訊
function buildLessonsMessage(venueName, lessons) {
  const lines = [`地點：${venueName}`];
  lessons.forEach((l, i) => {
    lines.push(`第${chineseNumber(i + 1)}堂課：${mdWithWeekday(l.date)}${hhmm(l.start)}～${hhmm(l.end)}`);
  });
  return lines.join("\n");
}

async function copyText(text, statusEl) {
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
  statusEl.textContent = "已複製";
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
  const preferred = document.getElementById("r-preferred").value;
  if (venueIds.length === 0) {
    status.textContent = "請至少勾選一個場館";
    return;
  }
  if (preferred && venueIds.length !== 1) {
    status.textContent = "指定希望時段時，請只勾一個場館（只在同一個館換時段）";
    return;
  }
  const [timeFrom, timeTo] = recurringTimeRange();
  const common = {
    weekday: Number(document.getElementById("r-weekday").value),
    date_from: document.getElementById("r-date-from").value,
    weeks: Number(document.getElementById("r-weeks").value),
    time_from: timeFrom,
    time_to: timeTo,
    duration_minutes: Number(document.getElementById("r-duration").value),
  };
  lastSearch = { weekday: common.weekday, duration: common.duration_minutes };
  const button = document.getElementById("btn-recurring");
  button.disabled = true;
  status.textContent = "查詢中…";
  try {
    if (preferred) {
      const result = await api.post("/api/slot-search/recurring/plan", {
        ...common,
        preferred_start: preferred,
        venue_id: venueIds[0],
      });
      startPlan(result);
    } else {
      const result = await api.post("/api/slot-search/recurring", { ...common, venue_ids: venueIds });
      renderRecurring(result);
    }
    status.textContent = "";
  } catch (e) {
    status.textContent = `失敗：${e.message}`;
  } finally {
    button.disabled = false;
  }
}

// ---- 不指定時段：自動推薦 ----

function optionSummary(o, weeks) {
  return [
    o.skipped.length === 0 ? `${weeks} 週全部可以` : `需順延 ${o.skipped.length} 週`,
    `同館接課 ${o.adjacent_weeks} 週`,
    `當天本來就在這館 ${o.same_venue_weeks} 週`,
  ].join("｜");
}

function renderRecurring(result) {
  document.getElementById("r-plan-block").hidden = true;
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
            <strong>#${i + 1}　${weekday} ${hhmm(o.start_time)}-${hhmm(o.end_time)}　${escapeHtml(o.venue_name)}</strong>
            <span class="hint">${optionSummary(o, result.weeks)}</span>
          </div>
          <div>日期：${o.dates.map(md).join("、")}</div>
          ${o.skipped
            .map((s) => `<div class="hint">⚠ ${md(s.date)} 跳過：${escapeHtml(s.reason)}（只有你看得到）</div>`)
            .join("")}
          <div class="panel-actions">
            <button type="button" class="secondary" data-copy="${i}">複製給學生的訊息</button>
            <button type="button" class="secondary" data-package="${i}">建立課程套組</button>
            <span class="hint" data-copy-status="${i}"></span>
          </div>
        </div>`
      )
      .join("");
    const optionLessons = (o) => o.dates.map((d) => ({ date: d, start: o.start_time, end: o.end_time }));
    box.querySelectorAll("[data-copy]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const o = result.options[Number(btn.dataset.copy)];
        copyText(buildLessonsMessage(o.venue_name, optionLessons(o)), document.querySelector(`[data-copy-status="${btn.dataset.copy}"]`));
      })
    );
    box.querySelectorAll("[data-package]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const o = result.options[Number(btn.dataset.package)];
        openPackageModal({ venueId: o.venue_id, venueName: o.venue_name, lessons: optionLessons(o) });
      })
    );
  }
  document.getElementById("r-result-block").hidden = false;
}

// ---- 指定時段：逐週排排看 ----

function startPlan(result) {
  document.getElementById("r-result-block").hidden = true;
  currentPlan = result;
  // 預設：指定時段可以就用指定時段；撞課就先選最方便的替代時段；都沒有就跳過
  planChoices = result.week_plans.map((w) => {
    if (w.preferred_ok) return { kind: "pref" };
    if (w.alternatives.length) return { kind: "alt", alt: 0 };
    return { kind: "skip" };
  });
  const weekday = WEEKDAY_NAMES[Number(document.getElementById("r-weekday").value)];
  document.getElementById("r-plan-title").textContent =
    `逐週排排看：每${weekday} ${hhmm(result.preferred_start)}～${hhmm(result.preferred_end)}　${result.venue_name}，共 ${result.weeks} 堂`;
  document.getElementById("r-plan-copy-status").textContent = "";
  renderPlan();
  document.getElementById("r-plan-block").hidden = false;
}

function chosenSlot(w, c) {
  if (c.kind === "pref") return { start: currentPlan.preferred_start, end: currentPlan.preferred_end };
  if (c.kind === "suggest") return { start: w.suggestion.start_time, end: w.suggestion.end_time };
  if (c.kind === "alt") return { start: w.alternatives[c.alt].start_time, end: w.alternatives[c.alt].end_time };
  return null;
}

// 照順序取「不跳過」的週，取滿 weeks 堂為止；跳過幾週就往後順延幾週（最多到 API 多給的那 2 週）
function visibleWeekCount() {
  let lessons = 0;
  for (let i = 0; i < currentPlan.week_plans.length; i++) {
    if (planChoices[i].kind !== "skip") lessons += 1;
    if (lessons === currentPlan.weeks) return i + 1;
  }
  return currentPlan.week_plans.length;
}

// 目前每週選擇對應的實際上課清單（跳過的週不算），訊息跟建立套組都用這份
function planLessons() {
  const count = visibleWeekCount();
  const lessons = [];
  for (let i = 0; i < count; i++) {
    const slot = chosenSlot(currentPlan.week_plans[i], planChoices[i]);
    if (slot) lessons.push({ date: currentPlan.week_plans[i].date, ...slot });
  }
  return lessons;
}

function radio(i, value, label, checked, disabled = false) {
  return `<label class="plan-choice${disabled ? " disabled" : ""}">
    <input type="radio" name="plan-${i}" value="${value}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""} />${label}
  </label>`;
}

function renderPlan() {
  const count = visibleWeekCount();
  const rows = [];
  for (let i = 0; i < count; i++) {
    const w = currentPlan.week_plans[i];
    const c = planChoices[i];
    const prefLabel = `${hhmm(currentPlan.preferred_start)}～${hhmm(currentPlan.preferred_end)}（指定時段${w.preferred_adjacent ? "，剛好接課" : ""}）`;
    const options = [radio(i, "pref", prefLabel, c.kind === "pref", !w.preferred_ok)];
    if (w.suggestion) {
      options.push(
        radio(i, "suggest", `💡 改 ${hhmm(w.suggestion.start_time)}～${hhmm(w.suggestion.end_time)}，${escapeHtml(w.suggestion.note)}，比較方便`, c.kind === "suggest")
      );
    }
    w.alternatives.forEach((a, k) => {
      options.push(
        radio(i, `alt-${k}`, `${hhmm(a.start_time)}～${hhmm(a.end_time)}（${escapeHtml(a.note)}）`, c.kind === "alt" && c.alt === k)
      );
    });
    options.push(radio(i, "skip", "這週跳過，往後順延一週", c.kind === "skip"));

    const notes = [];
    if (!w.preferred_ok) notes.push(`⚠ 指定時段不行：${escapeHtml(w.preferred_reason)}`);
    if (w.suggestion) notes.push("💡 這天前後有課可以接");
    notes.push(
      w.day_busy.length
        ? `當天已有：${w.day_busy.map((b) => `${hm(b.start)}-${hm(b.end)} ${escapeHtml(b.venue_name)}`).join("、")}`
        : "當天沒有其他課"
    );
    const extra = i >= currentPlan.weeks ? `<div class="hint">順延補課</div>` : "";
    rows.push(`<tr class="${w.preferred_ok ? "" : "plan-clash"}">
      <td>${mdWithWeekday(w.date)}${extra}</td>
      <td>${options.join("")}</td>
      <td class="hint">${notes.join("<br />")}</td>
    </tr>`);
  }
  const tbody = document.getElementById("r-plan-rows");
  tbody.innerHTML = rows.join("");
  tbody.querySelectorAll('input[type="radio"]').forEach((el) =>
    el.addEventListener("change", () => {
      const i = Number(el.name.split("-")[1]);
      planChoices[i] = el.value.startsWith("alt-")
        ? { kind: "alt", alt: Number(el.value.slice(4)) }
        : { kind: el.value };
      renderPlan();
    })
  );

  const lessons = planLessons();
  document.getElementById("r-plan-warning").textContent =
    lessons.length < currentPlan.weeks
      ? `⚠ 目前只排得到 ${lessons.length} 堂（最多順延 2 週），還差 ${currentPlan.weeks - lessons.length} 堂，請改選替代時段或減少週數。`
      : "";
  document.getElementById("r-plan-message").value = buildLessonsMessage(currentPlan.venue_name, lessons);
}

// ---- 一鍵建立課程套組 ----

async function openPackageModal(pkg) {
  pendingPackage = pkg;
  const weekdayName = WEEKDAY_NAMES[lastSearch.weekday];
  document.getElementById("pk-summary").innerHTML =
    `${escapeHtml(pkg.venueName)}｜每堂 ${lastSearch.duration} 分鐘｜共 ${pkg.lessons.length} 堂<br />` +
    pkg.lessons.map((l) => `${mdWithWeekday(l.date)} ${hhmm(l.start)}～${hhmm(l.end)}`).join("、");
  document.getElementById("pk-name").value = `${weekdayName}固定 ${pkg.lessons.length} 堂`;
  document.getElementById("pk-purchased").value = toLocalDateString(new Date());
  document.getElementById("pk-coach-fee").value = "";
  document.getElementById("pk-venue-fee").value = "0";
  document.getElementById("pk-payment").value = "unpaid";
  document.getElementById("pk-new-student").hidden = true;
  document.getElementById("pk-student").disabled = false;
  document.getElementById("pk-new-name").value = "";
  document.getElementById("pk-status").textContent = "";
  const students = await api.get("/api/students");
  document.getElementById("pk-student").innerHTML = students
    .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
    .join("");
  document.getElementById("package-modal").classList.add("open");
}

function closePackageModal() {
  document.getElementById("package-modal").classList.remove("open");
}

// 套組的預設上課時間用出現最多次的那個（其他週照各自的時間建立）
function mostCommonStart(lessons) {
  const counts = {};
  lessons.forEach((l) => (counts[l.start] = (counts[l.start] || 0) + 1));
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
}

async function submitPackage(e) {
  e.preventDefault();
  const status = document.getElementById("pk-status");
  const coachFee = parseFloat(document.getElementById("pk-coach-fee").value);
  if (Number.isNaN(coachFee)) {
    status.textContent = "請填教練費";
    return;
  }
  const submit = document.getElementById("pk-submit");
  submit.disabled = true;
  status.textContent = "建立中…";
  try {
    let studentId = Number(document.getElementById("pk-student").value);
    if (!document.getElementById("pk-new-student").hidden) {
      const name = document.getElementById("pk-new-name").value.trim();
      if (!name) {
        status.textContent = "請填新學生的姓名";
        return;
      }
      const student = await api.post("/api/students", {
        name,
        tier: document.getElementById("pk-new-tier").value,
      });
      studentId = student.id;
    }
    const pkg = pendingPackage;
    const created = await api.post("/api/packages", {
      student_id: studentId,
      name: document.getElementById("pk-name").value.trim(),
      session_duration: lastSearch.duration,
      coach_fee_per_hour: coachFee,
      venue_fee_per_hour: parseFloat(document.getElementById("pk-venue-fee").value) || 0,
      purchased_date: document.getElementById("pk-purchased").value,
      recur_start_time: mostCommonStart(pkg.lessons),
      default_venue_id: pkg.venueId,
      payment_status: document.getElementById("pk-payment").value,
      sessions: pkg.lessons.map((l) => ({ date: l.date, start_time: l.start })),
      check_conflicts: true,
    });
    closePackageModal();
    document.getElementById("r-status").innerHTML =
      `✅ 已建立套組「${escapeHtml(created.name)}」，共 ${created.total_sessions} 堂，已加到行事曆。` +
      `<a href="/packages.html">到課程套組查看</a>`;
  } catch (err) {
    // 409 = 建立前檢查發現撞課，訊息會列出是哪幾堂
    status.textContent = `沒有建立：${err.message}`;
  } finally {
    submit.disabled = false;
  }
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
  const preferred = document.getElementById("r-preferred");
  preferred.innerHTML =
    `<option value="">不指定（自動推薦）</option>` +
    Array.from({ length: 14 }, (_, k) => {
      const h = String(8 + k).padStart(2, "0");
      return `<option value="${h}:00">${h}:00</option>`;
    }).join("");
  document.querySelectorAll('input[name="r-time-preset"]').forEach((el) =>
    el.addEventListener("change", () => {
      document.getElementById("r-custom-time").hidden = el.value !== "custom" || !el.checked;
    })
  );

  await venuesReady;
  renderVenueChecks(venues.map((v) => v.id), "r-venue-checks");
  await renderAreaButtons("r-area-buttons", "r-venue-checks");
  document.getElementById("btn-recurring").addEventListener("click", searchRecurring);
  document.getElementById("btn-plan-copy").addEventListener("click", () =>
    copyText(document.getElementById("r-plan-message").value, document.getElementById("r-plan-copy-status"))
  );
  document.getElementById("btn-plan-package").addEventListener("click", () => {
    const lessons = planLessons();
    if (lessons.length < currentPlan.weeks) {
      document.getElementById("r-plan-copy-status").textContent =
        `還差 ${currentPlan.weeks - lessons.length} 堂，先調整到排滿再建立`;
      return;
    }
    openPackageModal({ venueId: currentPlan.venue_id, venueName: currentPlan.venue_name, lessons });
  });
  document.getElementById("pk-new-student-toggle").addEventListener("click", () => {
    const box = document.getElementById("pk-new-student");
    box.hidden = !box.hidden;
    document.getElementById("pk-student").disabled = !box.hidden;
  });
  document.getElementById("pk-cancel").addEventListener("click", closePackageModal);
  document.getElementById("package-form").addEventListener("submit", submitPackage);
});
