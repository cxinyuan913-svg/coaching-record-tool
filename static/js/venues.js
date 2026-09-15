// 場地管理頁邏輯

let editingId = null;

async function loadVenues() {
  const venues = await api.get("/api/venues");
  const tbody = document.getElementById("venue-list");
  tbody.innerHTML = "";
  venues.forEach((v) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(v.name)}</td>
      <td>${escapeHtml(v.address || "")}</td>
      <td>${
        v.booking_open_days_before == null
          ? "隨時可訂"
          : `提前 ${v.booking_open_days_before} 天 ${v.booking_open_time}`
      }</td>
      <td>${escapeHtml(v.cancellation_policy || "")}</td>
      <td>
        <button class="secondary" data-action="edit" data-id="${v.id}">編輯</button>
        <button class="danger" data-action="delete" data-id="${v.id}">刪除</button>
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

function toggleAnytimeFields() {
  const anytime = document.getElementById("f-anytime").checked;
  document.getElementById("row-days").style.display = anytime ? "none" : "";
  document.getElementById("row-time").style.display = anytime ? "none" : "";
}

function openModal(venue) {
  editingId = venue ? venue.id : null;
  const isAnytime = !!venue && venue.booking_open_days_before == null;
  document.getElementById("modal-title").textContent = venue ? "編輯場地" : "新增場地";
  document.getElementById("f-name").value = venue ? venue.name : "";
  document.getElementById("f-address").value = venue ? venue.address || "" : "";
  document.getElementById("f-anytime").checked = isAnytime;
  document.getElementById("f-days").value =
    venue && venue.booking_open_days_before != null ? venue.booking_open_days_before : 0;
  document.getElementById("f-time").value =
    venue && venue.booking_open_time ? venue.booking_open_time.slice(0, 5) : "00:00";
  document.getElementById("f-policy").value = venue ? venue.cancellation_policy || "" : "";
  document.getElementById("f-note").value = venue ? venue.note || "" : "";
  toggleAnytimeFields();
  document.getElementById("venue-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("venue-modal").classList.remove("open");
}

async function handleSave(e) {
  e.preventDefault();
  const isAnytime = document.getElementById("f-anytime").checked;
  const payload = {
    name: document.getElementById("f-name").value.trim(),
    address: document.getElementById("f-address").value.trim() || null,
    booking_open_days_before: isAnytime
      ? null
      : parseInt(document.getElementById("f-days").value, 10) || 0,
    booking_open_time: isAnytime ? null : document.getElementById("f-time").value + ":00",
    cancellation_policy: document.getElementById("f-policy").value.trim() || null,
    note: document.getElementById("f-note").value.trim() || null,
  };
  if (!payload.name) {
    alert("請輸入場地名稱");
    return;
  }
  try {
    if (editingId) {
      await api.put(`/api/venues/${editingId}`, payload);
    } else {
      await api.post("/api/venues", payload);
    }
    closeModal();
    await loadVenues();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
}

async function handleListClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "edit") {
    const venue = await api.get(`/api/venues/${id}`);
    openModal(venue);
  } else if (btn.dataset.action === "delete") {
    if (await confirmDialog("確定要刪除這個場地嗎？")) {
      try {
        await api.delete(`/api/venues/${id}`);
        await loadVenues();
      } catch (err) {
        alert("刪除失敗：" + err.message);
      }
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadVenues();
  document.getElementById("btn-add").addEventListener("click", () => openModal(null));
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("venue-form").addEventListener("submit", handleSave);
  document.getElementById("venue-list").addEventListener("click", handleListClick);
  document.getElementById("f-anytime").addEventListener("change", toggleAnytimeFields);
});
