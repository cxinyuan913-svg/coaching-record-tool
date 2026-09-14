// 行事曆頁邏輯：月檢視 + 新增/編輯課程表單

let students = [];
let venues = [];
let editingLessonId = null;
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
  const billing = lesson.package_id ? "包制" : "單堂";
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

function initCalendar() {
  const calendarEl = document.getElementById("calendar");
  calendar = new FullCalendar.Calendar(calendarEl, {
    locale: "zh-tw",
    initialView: "dayGridMonth",
    headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek" },
    dayMaxEvents: 3,
    events: fetchEvents,
    dateClick: (info) => openCreateModal(info.dateStr),
    eventClick: (info) => openEditModal(parseInt(info.event.extendedProps.lessonId, 10)),
  });
  calendar.render();
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
  document.getElementById("modal-title").textContent = "新增課程";
  document.getElementById("f-student").selectedIndex = 0;
  document.getElementById("f-venue").selectedIndex = 0;
  document.getElementById("f-date").value = dateStr || "";
  document.getElementById("f-time").value = "";
  document.getElementById("f-duration").value = 60;
  document.getElementById("f-headcount").value = 1;
  document.getElementById("f-payment").value = "unpaid";
  document.getElementById("row-status").style.display = "none";
  document.getElementById("btn-delete").style.display = "none";
  refreshSuggestedPrice();
  document.getElementById("lesson-modal").classList.add("open");
}

async function openEditModal(lessonId) {
  const lesson = await api.get(`/api/lessons/${lessonId}`);
  editingLessonId = lesson.id;
  document.getElementById("modal-title").textContent = "編輯課程";
  document.getElementById("f-student").value = lesson.student_id;
  document.getElementById("f-venue").value = lesson.venue_id;
  document.getElementById("f-date").value = lesson.date;
  document.getElementById("f-time").value = lesson.start_time.slice(0, 5);
  document.getElementById("f-duration").value = lesson.duration;
  document.getElementById("f-headcount").value = lesson.headcount;
  document.getElementById("f-amount").value = lesson.revenue_amount;
  document.getElementById("f-payment").value = lesson.payment_status;
  document.getElementById("f-status").value = lesson.status;
  document.getElementById("row-status").style.display = "";
  document.getElementById("btn-delete").style.display = "";
  document.getElementById("lesson-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("lesson-modal").classList.remove("open");
}

async function handleSave(e) {
  e.preventDefault();
  const payload = {
    student_id: parseInt(document.getElementById("f-student").value, 10),
    venue_id: parseInt(document.getElementById("f-venue").value, 10),
    date: document.getElementById("f-date").value,
    start_time: document.getElementById("f-time").value + ":00",
    duration: parseInt(document.getElementById("f-duration").value, 10),
    headcount: parseInt(document.getElementById("f-headcount").value, 10),
    payment_status: document.getElementById("f-payment").value,
    revenue_amount: parseFloat(document.getElementById("f-amount").value),
  };
  try {
    if (editingLessonId) {
      payload.status = document.getElementById("f-status").value;
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
});
