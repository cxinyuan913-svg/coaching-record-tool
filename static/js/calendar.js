// 行事曆頁邏輯：月檢視 + 新增/編輯課程表單

let students = [];
let venues = [];
let editingLessonId = null;
let editingLesson = null;
let editingPackage = null;
let calendar = null;

// 一次預訂多堂（單堂收費）用的狀態：dateMode 為 "single" 或 "multi"
const WEEKDAY_LABEL = ["週日", "週一", "週二", "週三", "週四", "週五", "週六"];
let dateMode = "single";
let selectedDates = [];
let pickerViewYear = null;
let pickerViewMonth = null;

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
  populateSelect("f-student", students, (s) => s.name);
  populateSelect("f-venue", venues, (v) => v.name);
  populateTimeSelects("f-time-hour", "f-time-minute", true);
  populateDurationSelect("f-duration");
}

function toDateOnly(isoStr) {
  return isoStr.slice(0, 10);
}

function addDays(dateStr, delta) {
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() + delta);
  return toLocalDateString(d);
}

function statusClass(lesson) {
  if (lesson.status === "cancelled" || lesson.status === "leave") return "status-cancelled";
  return lesson.payment_status === "paid" ? "status-paid" : "status-unpaid";
}

// 依開始時間＋時長算出結束時間，回傳「顯示用字串」與「事件用的日期時間字串」；
// 用 Date 物件計算而非純文字加減分鐘，才能正確處理時長跨過午夜的情況
function computeEndTime(lesson) {
  const end = new Date(`${lesson.date}T${lesson.start_time}`);
  end.setMinutes(end.getMinutes() + lesson.duration);
  const pad = (n) => String(n).padStart(2, "0");
  return {
    label: `${pad(end.getHours())}:${pad(end.getMinutes())}`,
    dateTime: `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}T${pad(end.getHours())}:${pad(end.getMinutes())}:00`,
  };
}

function lessonToEvent(lesson) {
  let billing;
  if (!lesson.package_id) {
    billing = "單堂";
  } else if (lesson.sequence_no) {
    billing = `第${lesson.sequence_no}/${lesson.package_total_sessions}堂`;
  } else {
    billing = "順延堂";
  }
  const startLabel = lesson.start_time.slice(0, 5);
  const end = computeEndTime(lesson);
  return {
    id: String(lesson.id),
    title: `${startLabel}~${end.label} ${lesson.student_name} ${lesson.venue_name}（${billing}）`,
    start: `${lesson.date}T${lesson.start_time}`,
    end: end.dateTime,
    classNames: [statusClass(lesson)],
    extendedProps: { lessonId: lesson.id },
  };
}

async function fetchEvents(fetchInfo, successCallback, failureCallback) {
  try {
    const start = toDateOnly(fetchInfo.startStr);
    const end = addDays(toDateOnly(fetchInfo.endStr), -1);
    const lessons = await api.get(`/api/lessons?start=${start}&end=${end}`);
    successCallback(lessons.map(lessonToEvent));
  } catch (err) {
    failureCallback(err);
  }
}

const mobileQuery = window.matchMedia("(max-width: 640px)");

function applyResponsiveView() {
  if (!calendar) return;
  const isMobile = mobileQuery.matches;
  const targetView = isMobile ? "listWeek" : "dayGridMonth";
  if (calendar.view.type !== targetView) {
    calendar.changeView(targetView);
  }
  calendar.setOption(
    "headerToolbar",
    isMobile
      ? { left: "prev,next today", center: "title", right: "" }
      : { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek" }
  );
}

function initCalendar() {
  const calendarEl = document.getElementById("calendar");
  calendar = new FullCalendar.Calendar(calendarEl, {
    locale: "zh-tw",
    initialView: mobileQuery.matches ? "listWeek" : "dayGridMonth",
    headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek" },
    dayMaxEvents: 3,
    displayEventTime: false, // 時段已經手動組進 title（13:00~14:00），不用 FullCalendar 自己再加一次
    events: fetchEvents,
    dateClick: (info) => openCreateModal(info.dateStr),
    eventClick: (info) => openEditModal(parseInt(info.event.extendedProps.lessonId, 10)),
    dayCellClassNames: (arg) => (isHoliday(toLocalDateString(arg.date)) ? ["fc-day-holiday"] : []),
    dayCellDidMount: (arg) => {
      const name = holidayName(toLocalDateString(arg.date));
      if (!name) return;
      const label = document.createElement("span");
      label.className = "holiday-label";
      label.textContent = name;
      arg.el.querySelector(".fc-daygrid-day-top")?.appendChild(label);
    },
  });
  calendar.render();
  applyResponsiveView();
  mobileQuery.addEventListener("change", applyResponsiveView);
}

async function refreshSuggestedPrice() {
  const duration = parseInt(document.getElementById("f-duration").value, 10) || 60;

  if (editingPackage) {
    // 套組課程：金額由套組費率 × 時長算出，不查價目表
    const hours = duration / 60;
    document.getElementById("f-amount").value =
      Math.round(editingPackage.coach_fee_per_hour * hours * 100) / 100;
    document.getElementById("f-venue-fee").value =
      Math.round(editingPackage.venue_fee_per_hour * hours * 100) / 100;
    updateTotalAmountDisplay();
    return;
  }

  const studentId = parseInt(document.getElementById("f-student").value, 10);
  const headcount = parseInt(document.getElementById("f-headcount").value, 10) || 1;
  const student = students.find((s) => s.id === studentId);
  if (!student) return;
  try {
    const result = await api.get(
      `/api/price_rules/resolve?tier=${student.tier}&headcount=${headcount}&duration=${duration}`
    );
    document.getElementById("f-amount").value = result.price;
    updateTotalAmountDisplay();
  } catch (err) {
    // 查無對應價目規則時，保留原金額讓使用者手動輸入
  }
}

function updateTotalAmountDisplay() {
  const coachFee = parseFloat(document.getElementById("f-amount").value) || 0;
  const venueFee = parseFloat(document.getElementById("f-venue-fee").value) || 0;
  document.getElementById("total-amount-display").textContent = coachFee + venueFee;
}

// 新增課程時，依所選學生列出還有剩餘額度的「臨時約時間」套組，可選擇掛上去；
// 有額度可約的話直接預設選起來，不用每次手動改
async function loadPackageOptionsForStudent() {
  const studentId = parseInt(document.getElementById("f-student").value, 10);
  const select = document.getElementById("f-package");
  select.innerHTML = '<option value="">不屬於套組（單堂計費）</option>';
  if (studentId) {
    const packages = await api.get(`/api/packages?student_id=${studentId}&status=active`);
    const available = packages.filter((p) => p.available_sessions > 0);
    available.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.name}（還剩${p.available_sessions}堂可約）`;
      select.appendChild(opt);
    });
    if (available.length > 0) select.value = String(available[0].id);
  }
  await handlePackageSelectChange();
}

// 選擇／取消選擇套組時，帶入套組的預設時段與費率，並鎖住金額／收款狀態（由套組控管）
async function handlePackageSelectChange() {
  const val = document.getElementById("f-package").value;
  if (!val) {
    editingPackage = null;
    document.getElementById("f-amount").disabled = false;
    document.getElementById("f-venue-fee").disabled = false;
    document.getElementById("f-payment").disabled = false;
    document.getElementById("package-note").style.display = "none";
  } else {
    editingPackage = await api.get(`/api/packages/${val}`);
    document.getElementById("f-venue").value = editingPackage.default_venue_id;
    document.getElementById("f-duration").value = editingPackage.session_duration;
    setTimeSelectValue("f-time-hour", "f-time-minute", editingPackage.recur_start_time.slice(0, 5));
    document.getElementById("f-payment").value = editingPackage.payment_status;
    document.getElementById("f-amount").disabled = true;
    document.getElementById("f-venue-fee").disabled = true;
    document.getElementById("f-payment").disabled = true;
    document.getElementById("package-note").style.display = "";
  }
  refreshSuggestedPrice();
  updateTotalAmountDisplay();
}

// ===== 一次預訂多堂：月曆點選多個日期（做法與課程套組頁的日期挑選一致）=====

function formatDateChip(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()}（${WEEKDAY_LABEL[d.getDay()][1]}）`;
}

function renderDateList() {
  selectedDates.sort();
  const ul = document.getElementById("l-date-list");
  ul.innerHTML = "";
  selectedDates.forEach((dateStr) => {
    const li = document.createElement("li");
    li.style.cssText =
      "background:#eef0f4;border-radius:4px;padding:4px 8px;display:flex;align-items:center;gap:6px;font-size:13px";
    li.innerHTML = `${formatDateChip(dateStr)} <button type="button" class="danger" data-remove-date="${dateStr}" style="padding:1px 6px">×</button>`;
    ul.appendChild(li);
  });
  document.getElementById("l-date-count").textContent = selectedDates.length;
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
  const start = document.getElementById("l-quick-start").value;
  const interval = parseInt(document.getElementById("l-quick-interval").value, 10) || 7;
  const count = parseInt(document.getElementById("l-quick-count").value, 10) || 0;
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
  document.getElementById("l-picker-label").textContent = `${pickerViewYear}年${pickerViewMonth + 1}月`;
  const grid = document.getElementById("l-picker-grid");
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

// 切換「單一日期」／「一次預訂多堂」：顯示狀態與 required 一定要一起改——
// 隱藏起來的 required 欄位會讓瀏覽器悄悄擋下送出，又不給任何錯誤訊息
// （新增套組表單曾經踩過同一個坑）。
function setDateMode(mode) {
  dateMode = mode;
  const multi = mode === "multi";
  document.getElementById("mode-single-date").checked = !multi;
  document.getElementById("mode-multi-date").checked = multi;
  document.getElementById("row-date").style.display = multi ? "none" : "";
  document.getElementById("f-date").required = !multi;
  document.getElementById("row-multi-dates").style.display = multi ? "" : "none";
  document.getElementById("multi-date-note").style.display = multi ? "" : "none";
  // 批次建立一律是單堂計費、建成未收款，所以套組與收款狀態這兩欄不適用
  document.getElementById("row-package").style.display = multi ? "none" : "";
  document.getElementById("row-payment").style.display = multi ? "none" : "";
  if (multi) {
    document.getElementById("f-package").value = "";
    document.getElementById("f-payment").value = "unpaid";
    handlePackageSelectChange();
    renderDateList();
    renderDatePicker();
  }
}

function openCreateModal(dateStr) {
  if (students.length === 0 || venues.length === 0) {
    alert("請先至「學生管理」與「場地管理」新增資料");
    return;
  }
  editingLessonId = null;
  editingLesson = null;
  editingPackage = null;
  document.getElementById("modal-title").textContent = "新增課程";
  document.getElementById("row-package").style.display = "";
  document.getElementById("f-student").selectedIndex = 0;
  document.getElementById("f-venue").selectedIndex = 0;
  document.getElementById("f-date").value = dateStr || "";
  document.getElementById("row-date-mode").style.display = "";
  selectedDates = [];
  document.getElementById("l-quick-start").value = dateStr || "";
  const pickerBase = dateStr ? new Date(dateStr + "T00:00:00") : new Date();
  setPickerView(pickerBase.getFullYear(), pickerBase.getMonth());
  setDateMode("single");
  document.getElementById("f-time-hour").value = "";
  document.getElementById("f-time-minute").value = "00";
  document.getElementById("f-duration").value = 60;
  document.getElementById("f-headcount").value = 1;
  document.getElementById("f-payment").value = "unpaid";
  document.getElementById("f-amount").disabled = false;
  document.getElementById("f-payment").disabled = false;
  document.getElementById("f-venue-fee").disabled = false;
  document.getElementById("f-venue-fee").value = 0;
  document.getElementById("package-note").style.display = "none";
  document.getElementById("row-status").style.display = "none";
  document.getElementById("btn-delete").style.display = "none";
  document.getElementById("adjustments-section").style.display = "none";
  loadPackageOptionsForStudent();
  document.getElementById("lesson-modal").classList.add("open");
}

async function openEditModal(lessonId) {
  // 編輯永遠是針對一堂課，多日期模式不適用
  setDateMode("single");
  document.getElementById("row-date-mode").style.display = "none";
  const lesson = await api.get(`/api/lessons/${lessonId}`);
  editingLessonId = lesson.id;
  editingLesson = lesson;
  const isPackage = !!lesson.package_id;
  editingPackage = isPackage ? await api.get(`/api/packages/${lesson.package_id}`) : null;
  document.getElementById("modal-title").textContent = "編輯課程";
  document.getElementById("row-package").style.display = "none";
  document.getElementById("f-student").value = lesson.student_id;
  document.getElementById("f-venue").value = lesson.venue_id;
  document.getElementById("f-date").value = lesson.date;
  setTimeSelectValue("f-time-hour", "f-time-minute", lesson.start_time.slice(0, 5));
  document.getElementById("f-duration").value = lesson.duration;
  document.getElementById("f-headcount").value = lesson.headcount;
  document.getElementById("f-amount").value = lesson.revenue_amount;
  document.getElementById("f-venue-fee").value = lesson.venue_fee_amount;
  document.getElementById("f-payment").value = lesson.payment_status;
  document.getElementById("f-status").value = lesson.status;
  document.getElementById("f-amount").disabled = isPackage;
  document.getElementById("f-venue-fee").disabled = isPackage;
  document.getElementById("f-payment").disabled = isPackage;
  document.getElementById("package-note").style.display = isPackage ? "" : "none";
  document.getElementById("row-status").style.display = "";
  document.getElementById("btn-delete").style.display = "";
  updateTotalAmountDisplay();

  const venue = venues.find((v) => v.id === lesson.venue_id);
  document.getElementById("cancellation-policy-hint").textContent = venue?.cancellation_policy
    ? `${venue.name} 取消／改期規定：${venue.cancellation_policy}`
    : "";
  document.getElementById("adjustments-section").style.display = "";
  await loadAdjustments();

  document.getElementById("lesson-modal").classList.add("open");
}

async function loadAdjustments() {
  const ADJ_TYPE_LABEL = {
    headcount_diff: "人數差額",
    venue_fee: "場地費",
    venue_change: "臨時改場地",
    other: "其他",
  };
  const adjustments = await api.get(`/api/adjustments?lesson_id=${editingLessonId}`);
  const tbody = document.getElementById("adjustment-list");
  tbody.innerHTML = "";
  if (adjustments.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">無額外費用</td></tr>';
    return;
  }
  adjustments.forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${ADJ_TYPE_LABEL[a.type] || a.type}</td>
      <td>${a.amount}</td>
      <td>${a.note ? a.note.replace(/</g, "&lt;") : ""}</td>
      <td>${a.settled ? "已結清" : "未結清"}</td>
      <td>
        ${
          a.settled
            ? ""
            : `<button type="button" class="secondary" data-action="settle-adj" data-id="${a.id}">結清</button>
               <button type="button" class="danger" data-action="delete-adj" data-id="${a.id}">刪除</button>`
        }
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function handleAddAdjustment() {
  const amount = parseFloat(document.getElementById("adj-amount").value);
  if (Number.isNaN(amount)) {
    alert("請輸入金額");
    return;
  }
  const payload = {
    lesson_id: editingLessonId,
    type: document.getElementById("adj-type").value,
    amount,
    note: document.getElementById("adj-note").value.trim() || null,
  };
  try {
    await api.post("/api/adjustments", payload);
    document.getElementById("adj-amount").value = "";
    document.getElementById("adj-note").value = "";
    await loadAdjustments();
  } catch (err) {
    alert("新增失敗：" + err.message);
  }
}

async function handleAdjustmentListClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "delete-adj" && !(await confirmDialog("確定要刪除這筆額外費用嗎？"))) {
    return;
  }
  try {
    if (btn.dataset.action === "settle-adj") {
      await api.patch(`/api/adjustments/${id}/settle`, {});
    } else if (btn.dataset.action === "delete-adj") {
      await api.delete(`/api/adjustments/${id}`);
    } else {
      return;
    }
    await loadAdjustments();
  } catch (err) {
    alert("操作失敗：" + err.message);
  }
}

function closeModal() {
  document.getElementById("lesson-modal").classList.remove("open");
}

async function handleLeaveFlow() {
  let body = {};
  for (;;) {
    try {
      await api.post(`/api/lessons/${editingLessonId}/leave`, body);
      return true;
    } catch (err) {
      const retryDate = prompt(
        `${err.message}\n請輸入順延日期（YYYY-MM-DD），取消則放棄請假`,
        ""
      );
      if (!retryDate) return false;
      body = { makeup_date: retryDate };
    }
  }
}

async function handleSave(e) {
  e.preventDefault();

  // 一次預訂多堂：走批次端點。每堂獨立、一律未收款、不掛套組；
  // 只要有一天撞課，後端會整批退回並列出是哪幾天。
  if (!editingLessonId && dateMode === "multi") {
    if (selectedDates.length === 0) {
      alert("請至少在月曆上選一個上課日期");
      return;
    }
    const batchPayload = {
      student_id: parseInt(document.getElementById("f-student").value, 10),
      venue_id: parseInt(document.getElementById("f-venue").value, 10),
      dates: selectedDates,
      start_time: getTimeSelectValue("f-time-hour", "f-time-minute") + ":00",
      duration: parseInt(document.getElementById("f-duration").value, 10),
      headcount: parseInt(document.getElementById("f-headcount").value, 10),
      revenue_amount: parseFloat(document.getElementById("f-amount").value),
      venue_fee_amount: parseFloat(document.getElementById("f-venue-fee").value) || 0,
    };
    try {
      const result = await api.post("/api/lessons/batch", batchPayload);
      closeModal();
      calendar.refetchEvents();
      alert(`已建立 ${result.created} 堂課，全部為未收款`);
    } catch (err) {
      alert("建立失敗：" + err.message);
    }
    return;
  }
  const newStatus = document.getElementById("f-status").value;
  const isPackage = editingLesson && !!editingLesson.package_id;

  if (editingLessonId && isPackage && newStatus === "leave" && editingLesson.status !== "leave") {
    const ok = await handleLeaveFlow();
    if (ok) {
      closeModal();
      calendar.refetchEvents();
    }
    return;
  }

  const payload = {
    student_id: parseInt(document.getElementById("f-student").value, 10),
    venue_id: parseInt(document.getElementById("f-venue").value, 10),
    date: document.getElementById("f-date").value,
    start_time: getTimeSelectValue("f-time-hour", "f-time-minute") + ":00",
    duration: parseInt(document.getElementById("f-duration").value, 10),
    headcount: parseInt(document.getElementById("f-headcount").value, 10),
    payment_status: document.getElementById("f-payment").value,
    revenue_amount: parseFloat(document.getElementById("f-amount").value),
    venue_fee_amount: parseFloat(document.getElementById("f-venue-fee").value) || 0,
  };
  try {
    if (editingLessonId) {
      payload.status = newStatus;
      await api.put(`/api/lessons/${editingLessonId}`, payload);
    } else {
      const packageId = document.getElementById("f-package").value;
      if (packageId) payload.package_id = parseInt(packageId, 10);
      await api.post("/api/lessons", payload);
    }
    closeModal();
    calendar.refetchEvents();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
}

async function handleDelete() {
  if (!editingLessonId) return;
  if (!(await confirmDialog("確定要刪除這堂課嗎？"))) return;
  try {
    await api.delete(`/api/lessons/${editingLessonId}`);
    closeModal();
    calendar.refetchEvents();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadOptions();
  initCalendar();
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("btn-delete").addEventListener("click", handleDelete);
  document.getElementById("lesson-form").addEventListener("submit", handleSave);
  document.getElementById("f-student").addEventListener("change", async () => {
    await loadPackageOptionsForStudent();
    // 多日期模式不吃套組，換學生時別讓「有額度就自動選套組」把金額欄位鎖住
    if (dateMode === "multi") {
      document.getElementById("f-package").value = "";
      await handlePackageSelectChange();
    }
  });
  document.getElementById("mode-single-date").addEventListener("change", () => setDateMode("single"));
  document.getElementById("mode-multi-date").addEventListener("change", () => setDateMode("multi"));
  document.getElementById("l-picker-prev").addEventListener("click", () => shiftPickerMonth(-1));
  document.getElementById("l-picker-next").addEventListener("click", () => shiftPickerMonth(1));
  document.getElementById("l-picker-grid").addEventListener("click", handlePickerGridClick);
  document.getElementById("l-date-list").addEventListener("click", handleDateListClick);
  document.getElementById("l-btn-quick-fill").addEventListener("click", handleQuickFill);
  document.getElementById("f-package").addEventListener("change", handlePackageSelectChange);
  document.getElementById("f-headcount").addEventListener("input", refreshSuggestedPrice);
  document.getElementById("f-duration").addEventListener("change", refreshSuggestedPrice);
  document.getElementById("f-amount").addEventListener("input", updateTotalAmountDisplay);
  document.getElementById("f-venue-fee").addEventListener("input", updateTotalAmountDisplay);
  document.getElementById("btn-add-adjustment").addEventListener("click", handleAddAdjustment);
  document.getElementById("adjustment-list").addEventListener("click", handleAdjustmentListClick);
  document.getElementById("btn-add-lesson").addEventListener("click", () => {
    openCreateModal(toLocalDateString(new Date()));
  });
});
