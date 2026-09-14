// 訂場檢查頁邏輯

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatCountdown(openAtStr) {
  const openAt = new Date(openAtStr);
  const diffMs = openAt - new Date();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  return `${openAt.toLocaleString("zh-Hant-TW")}（約 ${days} 天後開放）`;
}

async function loadBookingCheck() {
  const data = await api.get("/api/booking/check");
  renderNeedBooking(data.need_booking);
  renderNotYetOpen(data.not_yet_open);
  renderBooked(data.booked);
}

function renderNeedBooking(items) {
  const tbody = document.getElementById("need-booking");
  tbody.innerHTML = "";
  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">目前沒有需要訂場的課程</td></tr>';
    return;
  }
  items.forEach(({ lesson }) => {
    const tr = document.createElement("tr");
    const statusLabel = lesson.booking_status === "failed" ? "搶場失敗，需重訂" : "未訂場";
    tr.innerHTML = `
      <td>${lesson.date} ${lesson.start_time.slice(0, 5)}</td>
      <td>${escapeHtml(lesson.student_name)}</td>
      <td>${escapeHtml(lesson.venue_name)}</td>
      <td>${statusLabel}</td>
      <td><button data-action="mark-booked" data-id="${lesson.id}">標記已訂</button></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderNotYetOpen(items) {
  const tbody = document.getElementById("not-yet-open");
  tbody.innerHTML = "";
  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4">沒有尚未開放的場次</td></tr>';
    return;
  }
  items.forEach(({ lesson, booking_open_at }) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${lesson.date} ${lesson.start_time.slice(0, 5)}</td>
      <td>${escapeHtml(lesson.student_name)}</td>
      <td>${escapeHtml(lesson.venue_name)}</td>
      <td>${formatCountdown(booking_open_at)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderBooked(items) {
  const tbody = document.getElementById("already-booked");
  tbody.innerHTML = "";
  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">目前沒有已訂場次</td></tr>';
    return;
  }
  items.forEach(({ lesson }) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${lesson.date} ${lesson.start_time.slice(0, 5)}</td>
      <td>${escapeHtml(lesson.student_name)}</td>
      <td>${escapeHtml(lesson.venue_name)}</td>
      <td>${lesson.booked_at ? new Date(lesson.booked_at).toLocaleString("zh-Hant-TW") : ""}</td>
      <td><button class="secondary" data-action="unmark-booked" data-id="${lesson.id}">取消已訂</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function handleClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  try {
    if (btn.dataset.action === "mark-booked") {
      await api.patch(`/api/booking/${id}`, { booking_status: "booked" });
    } else if (btn.dataset.action === "unmark-booked") {
      await api.patch(`/api/booking/${id}`, { booking_status: "not_booked" });
    } else {
      return;
    }
    await loadBookingCheck();
  } catch (err) {
    alert("更新失敗：" + err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadBookingCheck();
  document.querySelector("main").addEventListener("click", handleClick);
});
