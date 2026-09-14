// 行事曆頁邏輯：月檢視 + 新增/編輯課程表單

let students = [];
let venues = [];
let editingLessonId = null;
let editingLesson = null;
let calendar = null;

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
  return d.toISOString().slice(0, 10);
}

function statusClass(lesson) {
  if (lesson.status === "cancelled" || lesson.status === "leave") return "status-cancelled";
  return lesson.payment_status === "paid" ? "status-paid" : "status-unpaid";
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
  return {
    id: String(lesson.id),
    title: `${lesson.start_time.slice(0, 5)} ${lesson.student_name} ${lesson.venue_name}（${billing}）`,
    start: `${lesson.date}T${lesson.start_time}`,
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
    events: fetchEvents,
    dateClick: (info) => openCreateModal(info.dateStr),
    eventClick: (info) => openEditModal(parseInt(info.event.extendedProps.lessonId, 10)),
  });
  calendar.render();
  applyResponsiveView();
  mobileQuery.addEventListener("change", applyResponsiveView);
}

async function refreshSuggestedPrice() {
  const studentId = parseInt(document.getElementById("f-student").value, 10);
  const headcount = parseInt(document.getElementById("f-headcount").value, 10) || 1;
  const student = students.find((s) => s.id === studentId);
  if (!student) return;
  try {
    const result = await api.get(
      `/api/price_rules/resolve?tier=${student.tier}&headcount=${headcount}`
    );
    document.getElementById("f-amount").value = result.price;
  } catch (err) {
    // 查無對應價目規則時，保留原金額讓使用者手動輸入
  }
}

function openCreateModal(dateStr) {
  if (students.length === 0 || venues.length === 0) {
    alert("請先至「學生管理」與「場地管理」新增資料");
    return;
  }
  editingLessonId = null;
  editingLesson = null;
  document.getElementById("modal-title").textContent = "新增課程";
  document.getElementById("f-student").selectedIndex = 0;
  document.getElementById("f-venue").selectedIndex = 0;
  document.getElementById("f-date").value = dateStr || "";
  document.getElementById("f-time-hour").value = "";
  document.getElementById("f-time-minute").value = "";
  document.getElementById("f-duration").value = 60;
  document.getElementById("f-headcount").value = 1;
  document.getElementById("f-payment").value = "unpaid";
  document.getElementById("f-amount").disabled = false;
  document.getElementById("f-payment").disabled = false;
  document.getElementById("package-note").style.display = "none";
  document.getElementById("row-status").style.display = "none";
  document.getElementById("btn-delete").style.display = "none";
  document.getElementById("adjustments-section").style.display = "none";
  refreshSuggestedPrice();
  document.getElementById("lesson-modal").classList.add("open");
}

async function openEditModal(lessonId) {
  const lesson = await api.get(`/api/lessons/${lessonId}`);
  editingLessonId = lesson.id;
  editingLesson = lesson;
  const isPackage = !!lesson.package_id;
  document.getElementById("modal-title").textContent = "編輯課程";
  document.getElementById("f-student").value = lesson.student_id;
  document.getElementById("f-venue").value = lesson.venue_id;
  document.getElementById("f-date").value = lesson.date;
  setTimeSelectValue("f-time-hour", "f-time-minute", lesson.start_time.slice(0, 5));
  document.getElementById("f-duration").value = lesson.duration;
  document.getElementById("f-headcount").value = lesson.headcount;
  document.getElementById("f-amount").value = lesson.revenue_amount;
  document.getElementById("f-payment").value = lesson.payment_status;
  document.getElementById("f-status").value = lesson.status;
  document.getElementById("f-amount").disabled = isPackage;
  document.getElementById("f-payment").disabled = isPackage;
  document.getElementById("package-note").style.display = isPackage ? "" : "none";
  document.getElementById("row-status").style.display = "";
  document.getElementById("btn-delete").style.display = "";

  const venue = venues.find((v) => v.id === lesson.venue_id);
  document.getElementById("cancellation-policy-hint").textContent = venue?.cancellation_policy
    ? `${venue.name} 取消／改期規定：${venue.cancellation_policy}`
    : "";
  document.getElementById("adjustments-section").style.display = "";
  await loadAdjustments();

  document.getElementById("lesson-modal").classList.add("open");
}

async function loadAdjustments() {
  const ADJ_TYPE_LABEL = { headcount_diff: "人數差額", venue_fee: "場地費", other: "其他" };
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
  };
  try {
    if (editingLessonId) {
      payload.status = newStatus;
      await api.put(`/api/lessons/${editingLessonId}`, payload);
    } else {
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
  if (!confirm("確定要刪除這堂課嗎？")) return;
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
  document.getElementById("f-student").addEventListener("change", refreshSuggestedPrice);
  document.getElementById("f-headcount").addEventListener("input", refreshSuggestedPrice);
  document.getElementById("btn-add-adjustment").addEventListener("click", handleAddAdjustment);
  document.getElementById("adjustment-list").addEventListener("click", handleAdjustmentListClick);
  document.getElementById("btn-add-lesson").addEventListener("click", () => {
    openCreateModal(new Date().toISOString().slice(0, 10));
  });
});
