// 課程套組管理頁邏輯

const TIER_LABEL = { new: "新生", friend: "朋友", regular: "熟客" };
const WEEKDAY_LABEL = ["週日", "週一", "週二", "週三", "週四", "週五", "週六"];
const STATUS_LABEL = { active: "進行中", completed: "已完成", expired: "已過期" };

// 收款訊息固定附上的匯款資訊，之後帳戶異動直接改這裡即可
const BANK_INFO = "匯款資訊：\n台灣土地銀行（005）\n帳號：076005521269";

let students = [];
let venues = [];
let editingId = null;
let isEditMode = false;
let selectedDates = []; // 新增套組時手動選的上課日期（YYYY-MM-DD 字串）
let pickerViewYear = null; // 上課日期月曆目前顯示的年份
let pickerViewMonth = null; // 上課日期月曆目前顯示的月份（0-11）
let scheduleMode = "dates"; // 新增套組時的上課日期安排方式："dates"=已排定日期／"adhoc"=臨時約時間

function populateSelect(id, items, labelFn) {
  const select = document.getElementById(id);
  select.innerHTML = "";
  items.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = labelFn(item);
    select.appendChild(opt);
  });
}

async function loadOptions() {
  [students, venues] = await Promise.all([api.get("/api/students"), api.get("/api/venues")]);
  populateSelect("f-student", students, (s) => `${s.name}（${TIER_LABEL[s.tier]}）`);
  populateSelect("f-venue", venues, (v) => v.name);
  populateTimeSelects("f-recur-time-hour", "f-recur-time-minute", false);
  populateDurationSelect("f-duration");
}

// 依「第一堂日期」自動推算每週固定上課星期幾，不需要另外詢問（編輯模式用）
function weekdayOfDate(dateStr) {
  if (!dateStr) return null;
  return new Date(dateStr + "T00:00:00").getDay();
}

function updateWeekdayHint() {
  const dateStr = document.getElementById("f-start-date").value;
  const weekday = weekdayOfDate(dateStr);
  document.getElementById("weekday-hint").textContent =
    weekday === null ? "" : `→ 每週${WEEKDAY_LABEL[weekday]}固定上課`;
}

// 上課日期清單（新增套組用）
function formatDateChip(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()}（${WEEKDAY_LABEL[d.getDay()][1]}）`;
}

function renderDateList() {
  selectedDates.sort();
  const ul = document.getElementById("date-list");
  ul.innerHTML = "";
  selectedDates.forEach((dateStr) => {
    const li = document.createElement("li");
    li.style.cssText =
      "background:#eef0f4;border-radius:4px;padding:4px 8px;display:flex;align-items:center;gap:6px;font-size:13px";
    li.innerHTML = `${formatDateChip(dateStr)} <button type="button" class="danger" data-remove-date="${dateStr}" style="padding:1px 6px">×</button>`;
    ul.appendChild(li);
  });
  document.getElementById("date-count").textContent = selectedDates.length;
  updateEstimatedTotal();
}

function addDate(dateStr) {
  if (!dateStr || selectedDates.includes(dateStr)) return;
  selectedDates.push(dateStr);
  renderDateList();
  renderDatePicker();
}

function removeDate(dateStr) {
  selectedDates = selectedDates.filter((d) => d !== dateStr);
  renderDateList();
  renderDatePicker();
}

function toggleDate(dateStr) {
  if (selectedDates.includes(dateStr)) {
    removeDate(dateStr);
  } else {
    addDate(dateStr);
  }
}

function handleQuickFill() {
  const start = document.getElementById("f-quick-start").value;
  const interval = parseInt(document.getElementById("f-quick-interval").value, 10) || 7;
  const count = parseInt(document.getElementById("f-quick-count").value, 10) || 0;
  if (!start || count < 1) {
    alert("請填「從」的日期與堂數");
    return;
  }
  const base = new Date(start + "T00:00:00");
  for (let i = 0; i < count; i++) {
    const d = new Date(base);
    d.setDate(d.getDate() + i * interval);
    addDate(toLocalDateString(d));
  }
  setPickerView(base.getFullYear(), base.getMonth());
}

function handleDateListClick(e) {
  const btn = e.target.closest("button[data-remove-date]");
  if (!btn) return;
  removeDate(btn.dataset.removeDate);
}

// 上課日期月曆（新增套組用）：點日期格子切換選取，可跨月翻頁累積選取
function setPickerView(year, month) {
  const d = new Date(year, month, 1);
  pickerViewYear = d.getFullYear();
  pickerViewMonth = d.getMonth();
  renderDatePicker();
}

function shiftPickerMonth(delta) {
  setPickerView(pickerViewYear, pickerViewMonth + delta);
}

function renderDatePicker() {
  if (pickerViewYear === null) return;
  document.getElementById("picker-label").textContent = `${pickerViewYear}年${pickerViewMonth + 1}月`;
  const grid = document.getElementById("picker-grid");
  grid.innerHTML = "";
  WEEKDAY_LABEL.forEach((w) => {
    const cell = document.createElement("div");
    cell.style.cssText = "font-weight:600;color:#888;padding:4px 0";
    cell.textContent = w[1];
    grid.appendChild(cell);
  });
  const startOffset = new Date(pickerViewYear, pickerViewMonth, 1).getDay();
  const daysInMonth = new Date(pickerViewYear, pickerViewMonth + 1, 0).getDate();
  for (let i = 0; i < startOffset; i++) {
    grid.appendChild(document.createElement("div"));
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = toLocalDateString(new Date(pickerViewYear, pickerViewMonth, day));
    const selected = selectedDates.includes(dateStr);
    const holiday = isHoliday(dateStr);
    const cell = document.createElement("button");
    cell.type = "button";
    cell.textContent = day;
    cell.dataset.date = dateStr;
    if (holiday) cell.title = holidayName(dateStr);
    let border = "#e0e0e0";
    let background = holiday ? "#fdf1ef" : "#fff";
    let color = holiday ? "#c0503c" : "#333";
    if (selected) {
      border = "#2a78d6";
      background = "#2a78d6";
      color = "#fff";
    }
    cell.style.cssText = `padding:6px 0;border:1px solid ${border};border-radius:4px;background:${background};color:${color};cursor:pointer;font-weight:${selected ? "600" : "400"}`;
    grid.appendChild(cell);
  }
}

function handlePickerGridClick(e) {
  const btn = e.target.closest("button[data-date]");
  if (!btn) return;
  toggleDate(btn.dataset.date);
}

// 新增套組時切換「已排定日期」／「臨時約時間」，控制欄位顯示與 required
function updateScheduleModeVisibility() {
  const adhoc = !isEditMode && scheduleMode === "adhoc";
  document.getElementById("row-session-dates").style.display =
    !isEditMode && scheduleMode === "dates" ? "" : "none";
  document.getElementById("row-total-sessions").style.display = isEditMode || adhoc ? "" : "none";
  document.getElementById("f-total-sessions").required = isEditMode || adhoc;
  updateEstimatedTotal();
}

// 預估總金額 = (堂課費+場地費)/小時 × 標準時長(小時) × 堂數，僅供表單即時預覽
function updateEstimatedTotal() {
  const coachFee = parseFloat(document.getElementById("f-coach-fee").value) || 0;
  const venueFee = parseFloat(document.getElementById("f-venue-fee").value) || 0;
  const duration = parseInt(document.getElementById("f-duration").value, 10) || 0;
  const sessions =
    isEditMode || scheduleMode === "adhoc"
      ? parseInt(document.getElementById("f-total-sessions").value, 10) || 0
      : selectedDates.length;
  const perSession = Math.round((coachFee + venueFee) * (duration / 60) * 100) / 100;
  const total = Math.round(perSession * sessions * 100) / 100;
  document.getElementById("per-session-display").textContent = perSession;
  document.getElementById("total-sessions-display").textContent = sessions;
  document.getElementById("total-price-display").textContent = total;
}

async function loadPackages() {
  const packages = await api.get("/api/packages");
  const tbody = document.getElementById("package-list");
  tbody.innerHTML = "";
  packages.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.student_name)}</td>
      <td>${escapeHtml(p.name)}</td>
      <td>${minutesToHourLabel(p.session_duration)}</td>
      <td>${p.remaining_sessions} / ${p.total_sessions}</td>
      <td>${p.price_per_session}</td>
      <td>${STATUS_LABEL[p.status] || p.status}</td>
      <td>
        <button class="secondary" data-action="toggle-payment" data-id="${p.id}" data-current="${p.payment_status}">
          ${p.payment_status === "paid" ? "已收款" : "未收款"}
        </button>
      </td>
      <td>
        <button class="secondary" data-action="edit" data-id="${p.id}">編輯</button>
        <button class="secondary" data-action="message" data-id="${p.id}">課程訊息</button>
        <button class="secondary" data-action="settlement" data-id="${p.id}">結算單</button>
        <button class="danger" data-action="delete" data-id="${p.id}">刪除</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function openModal(pkg) {
  editingId = pkg ? pkg.id : null;
  isEditMode = !!pkg;
  document.getElementById("modal-title").textContent = isEditMode ? "編輯套組" : "新增套組（批次排課）";
  document.getElementById("btn-save").textContent = isEditMode ? "儲存" : "儲存並批次排課";
  document.getElementById("f-student").disabled = isEditMode;
  document.getElementById("row-payment").style.display = isEditMode ? "none" : "";
  document.getElementById("edit-note").style.display = isEditMode ? "" : "none";
  document.getElementById("row-start-date").style.display = isEditMode ? "" : "none";
  document.getElementById("row-schedule-mode").style.display = isEditMode ? "none" : "";
  // 隱藏的欄位不能保留 required，否則 Chrome 仍會擋下表單送出
  document.getElementById("f-start-date").required = isEditMode;

  document.getElementById("f-student").value = pkg ? pkg.student_id : students[0]?.id ?? "";
  document.getElementById("f-venue").value = pkg ? pkg.default_venue_id : venues[0]?.id ?? "";
  document.getElementById("f-name").value = pkg ? pkg.name : "8堂1小時套組";
  document.getElementById("f-duration").value = pkg ? pkg.session_duration : "60";
  document.getElementById("f-coach-fee").value = pkg ? pkg.coach_fee_per_hour : "";
  document.getElementById("f-venue-fee").value = pkg ? pkg.venue_fee_per_hour : 0;
  document.getElementById("f-purchased-date").value = pkg
    ? pkg.purchased_date
    : toLocalDateString(new Date());

  if (isEditMode) {
    document.getElementById("f-total-sessions").value = pkg.total_sessions;
    document.getElementById("f-start-date").value = pkg.start_date;
    updateWeekdayHint();
  } else {
    selectedDates = [];
    document.getElementById("f-total-sessions").value = 8;
    document.getElementById("f-quick-start").value = "";
    document.getElementById("f-quick-interval").value = 7;
    document.getElementById("f-quick-count").value = 8;
    const today = new Date();
    setPickerView(today.getFullYear(), today.getMonth());
    scheduleMode = "dates";
    document.getElementById("mode-dates").checked = true;
    renderDateList();
  }

  setTimeSelectValue(
    "f-recur-time-hour",
    "f-recur-time-minute",
    pkg ? pkg.recur_start_time.slice(0, 5) : "18:00"
  );
  document.getElementById("f-payment").value = "unpaid";
  updateScheduleModeVisibility();
  document.getElementById("package-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("package-modal").classList.remove("open");
  document.getElementById("f-student").disabled = false;
}

async function handleSave(e) {
  e.preventDefault();
  const basePayload = {
    name: document.getElementById("f-name").value.trim(),
    session_duration: parseInt(document.getElementById("f-duration").value, 10),
    coach_fee_per_hour: parseFloat(document.getElementById("f-coach-fee").value),
    venue_fee_per_hour: parseFloat(document.getElementById("f-venue-fee").value) || 0,
    purchased_date: document.getElementById("f-purchased-date").value,
    recur_start_time: getTimeSelectValue("f-recur-time-hour", "f-recur-time-minute") + ":00",
    default_venue_id: parseInt(document.getElementById("f-venue").value, 10),
  };

  if (!basePayload.name || Number.isNaN(basePayload.coach_fee_per_hour)) {
    alert("請完整填寫表單");
    return;
  }

  try {
    if (editingId) {
      const totalSessions = parseInt(document.getElementById("f-total-sessions").value, 10);
      const startDate = document.getElementById("f-start-date").value;
      if (!startDate || !totalSessions || totalSessions < 1) {
        alert("請完整填寫表單（總堂數需至少為 1）");
        return;
      }
      await api.put(`/api/packages/${editingId}`, {
        ...basePayload,
        total_sessions: totalSessions,
        start_date: startDate,
        recur_weekday: weekdayOfDate(startDate),
      });
    } else if (scheduleMode === "adhoc") {
      const totalSessions = parseInt(document.getElementById("f-total-sessions").value, 10);
      if (!totalSessions || totalSessions < 1) {
        alert("請填寫預購堂數");
        return;
      }
      await api.post("/api/packages", {
        ...basePayload,
        total_sessions: totalSessions,
        student_id: parseInt(document.getElementById("f-student").value, 10),
        payment_status: document.getElementById("f-payment").value,
      });
    } else {
      if (selectedDates.length === 0) {
        alert("請至少選擇一個上課日期");
        return;
      }
      await api.post("/api/packages", {
        ...basePayload,
        session_dates: selectedDates,
        student_id: parseInt(document.getElementById("f-student").value, 10),
        payment_status: document.getElementById("f-payment").value,
      });
    }
    closeModal();
    await loadPackages();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
}

const ADJ_TYPE_LABEL = { headcount_diff: "人數差額", venue_fee: "場地費", other: "其他" };
let settlementPackageId = null;

async function openSettlementModal(packageId) {
  settlementPackageId = packageId;
  await refreshSettlement();
  document.getElementById("settlement-modal").classList.add("open");
}

async function refreshSettlement() {
  const data = await api.get(`/api/packages/${settlementPackageId}/settlement`);
  const tbody = document.getElementById("settlement-list");
  tbody.innerHTML = "";
  if (data.adjustments.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3">目前沒有未結清差額</td></tr>';
  } else {
    data.adjustments.forEach((a) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${ADJ_TYPE_LABEL[a.type] || a.type}</td>
        <td>${a.amount}</td>
        <td>${escapeHtml(a.note || "")}</td>
      `;
      tbody.appendChild(tr);
    });
  }
  document.getElementById("settlement-total").textContent = data.total;
}

async function handleSettleAll() {
  if (!settlementPackageId) return;
  try {
    await api.patch(`/api/packages/${settlementPackageId}/settlement/settle`, {});
    await refreshSettlement();
  } catch (err) {
    alert("結清失敗：" + err.message);
  }
}

// 課程訊息產生（可直接貼給學生）
function chineseNumber(n) {
  const digits = "〇一二三四五六七八九";
  if (n < 10) return digits[n];
  if (n < 20) return "十" + (n > 10 ? digits[n - 10] : "");
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  return digits[tens] + "十" + (ones ? digits[ones] : "");
}

function formatDateWithWeekday(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()}（${WEEKDAY_LABEL[d.getDay()][1]}）`;
}

function addMinutes(timeStr, minutes) {
  const [h, m] = timeStr.split(":").map(Number);
  const total = h * 60 + m + minutes;
  const rh = Math.floor(total / 60) % 24;
  const rm = total % 60;
  return `${String(rh).padStart(2, "0")}:${String(rm).padStart(2, "0")}`;
}

function buildLineMessage(pkg, lessons) {
  const totalHours = (pkg.total_sessions * pkg.session_duration) / 60;
  const [py, pm, pd] = pkg.purchased_date.split("-").map(Number);
  const lines = [];
  lines.push(`付費日期：${py}/${pm}/${pd}（${Math.round(pkg.total_price)}）`);
  lines.push(`羽球課程${totalHours}小時（場地費以${Math.round(pkg.venue_fee_per_hour)}元記）`);
  lines.push("");
  const active = lessons
    .filter((l) => l.status !== "leave")
    .slice()
    .sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time));
  active.forEach((lesson, idx) => {
    const start = lesson.start_time.slice(0, 5);
    const end = addMinutes(start, lesson.duration);
    lines.push(
      `第${chineseNumber(idx + 1)}堂課：${formatDateWithWeekday(lesson.date)}${start}～${end}`
    );
  });
  lines.push("");
  lines.push(BANK_INFO);
  return lines.join("\n");
}

async function openMessageModal(packageId) {
  const [pkg, lessons] = await Promise.all([
    api.get(`/api/packages/${packageId}`),
    api.get(`/api/packages/${packageId}/lessons`),
  ]);
  document.getElementById("message-text").value = buildLineMessage(pkg, lessons);
  document.getElementById("message-modal").classList.add("open");
}

async function handleCopyMessage() {
  const text = document.getElementById("message-text").value;
  try {
    await navigator.clipboard.writeText(text);
    alert("已複製到剪貼簿");
  } catch (err) {
    alert("複製失敗，請手動選取文字後 Ctrl+C");
  }
}

async function handleListClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "toggle-payment") {
    const next = btn.dataset.current === "paid" ? "unpaid" : "paid";
    try {
      await api.patch(`/api/packages/${id}/payment`, { payment_status: next });
      await loadPackages();
    } catch (err) {
      alert("更新收款狀態失敗：" + err.message);
    }
  } else if (btn.dataset.action === "edit") {
    const pkg = await api.get(`/api/packages/${id}`);
    openModal(pkg);
  } else if (btn.dataset.action === "message") {
    await openMessageModal(id);
  } else if (btn.dataset.action === "settlement") {
    await openSettlementModal(id);
  } else if (btn.dataset.action === "delete") {
    if (confirm("確定要刪除這個套組嗎？套組底下所有課程也會一併刪除。")) {
      try {
        await api.delete(`/api/packages/${id}`);
        await loadPackages();
      } catch (err) {
        alert("刪除失敗：" + err.message);
      }
    }
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadOptions();
  await loadPackages();
  document.getElementById("btn-add").addEventListener("click", () => openModal(null));
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("package-form").addEventListener("submit", handleSave);
  document.getElementById("package-list").addEventListener("click", handleListClick);
  document.getElementById("btn-settlement-close").addEventListener("click", () => {
    document.getElementById("settlement-modal").classList.remove("open");
  });
  document.getElementById("btn-settle-all").addEventListener("click", handleSettleAll);
  document.getElementById("btn-message-close").addEventListener("click", () => {
    document.getElementById("message-modal").classList.remove("open");
  });
  document.getElementById("btn-message-copy").addEventListener("click", handleCopyMessage);
  document.getElementById("f-start-date").addEventListener("change", updateWeekdayHint);
  document.getElementById("f-coach-fee").addEventListener("input", updateEstimatedTotal);
  document.getElementById("f-venue-fee").addEventListener("input", updateEstimatedTotal);
  document.getElementById("f-duration").addEventListener("change", updateEstimatedTotal);
  document.getElementById("f-total-sessions").addEventListener("input", updateEstimatedTotal);
  document.getElementById("btn-quick-fill").addEventListener("click", handleQuickFill);
  document.getElementById("date-list").addEventListener("click", handleDateListClick);
  document.getElementById("picker-prev").addEventListener("click", () => shiftPickerMonth(-1));
  document.getElementById("picker-next").addEventListener("click", () => shiftPickerMonth(1));
  document.getElementById("picker-grid").addEventListener("click", handlePickerGridClick);
  document.querySelectorAll('input[name="schedule-mode"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      scheduleMode = e.target.value;
      updateScheduleModeVisibility();
    });
  });
});
