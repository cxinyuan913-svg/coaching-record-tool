// 場地管理頁邏輯

let editingId = null;

async function loadVenues() {
  const venues = await api.get("/api/venues");
  // 場館數量很少（個位數），逐一查價目表筆數就好，不另外開彙總 API
  const feeCounts = await Promise.all(
    venues.map((v) => api.get(`/api/venues/${v.id}/fee-rates`).then((rows) => rows.length))
  );
  const tbody = document.getElementById("venue-list");
  tbody.innerHTML = "";
  venues.forEach((v, i) => {
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
      <td>${feeCounts[i] ? `${feeCounts[i]} 個時段` : '<span style="color: #c0392b">未設定</span>'}</td>
      <td>
        <button class="secondary" data-action="edit" data-id="${v.id}">編輯</button>
        <button class="secondary" data-action="fees" data-id="${v.id}" data-name="${escapeHtml(v.name)}">場地費</button>
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
  } else if (btn.dataset.action === "fees") {
    await openFeeModal(parseInt(id, 10), btn.dataset.name);
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

// ---------- 場地費價目表 ----------

const WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];
let feeVenueId = null;

function feeRowHtml(rate) {
  const days = WEEKDAY_LABELS.map(
    (label, d) =>
      `<label style="margin-right: 4px; white-space: nowrap">
        <input type="checkbox" class="fee-day" value="${d}" style="width: auto" ${rate.weekdays.includes(d) ? "checked" : ""} />${label}
      </label>`
  ).join("");
  return `<tr>
    <td>${days}</td>
    <td><input type="time" class="fee-start" value="${rate.start_time.slice(0, 5)}" /></td>
    <td><input type="time" class="fee-end" value="${rate.end_time.slice(0, 5)}" /></td>
    <td><input type="number" class="fee-price" min="0" step="10" value="${rate.fee_per_hour}" style="width: 90px" /></td>
    <td><button type="button" class="danger fee-remove">移除</button></td>
  </tr>`;
}

function showFeeError(message) {
  const el = document.getElementById("fee-error");
  el.textContent = message;
  el.style.display = message ? "" : "none";
}

async function openFeeModal(venueId, venueName) {
  feeVenueId = venueId;
  document.getElementById("fee-modal-title").textContent = `場地費價目表：${venueName}`;
  const rates = await api.get(`/api/venues/${venueId}/fee-rates`);
  document.getElementById("fee-rows").innerHTML = rates.map(feeRowHtml).join("");
  showFeeError("");
  document.getElementById("fee-modal").classList.add("open");
}

function closeFeeModal() {
  document.getElementById("fee-modal").classList.remove("open");
}

function addFeeRow() {
  // 新的一列預設帶「平日晚上」，最常見的情況，改起來最少
  document
    .getElementById("fee-rows")
    .insertAdjacentHTML(
      "beforeend",
      feeRowHtml({ weekdays: [0, 1, 2, 3, 4], start_time: "18:00", end_time: "23:00", fee_per_hour: 0 })
    );
}

async function saveFees() {
  const rows = [...document.querySelectorAll("#fee-rows tr")];
  const items = rows.map((tr) => ({
    weekdays: [...tr.querySelectorAll(".fee-day:checked")].map((c) => parseInt(c.value, 10)),
    start_time: tr.querySelector(".fee-start").value,
    end_time: tr.querySelector(".fee-end").value,
    fee_per_hour: parseFloat(tr.querySelector(".fee-price").value),
  }));
  const bad = items.findIndex(
    (it) => !it.weekdays.length || !it.start_time || !it.end_time || Number.isNaN(it.fee_per_hour)
  );
  if (bad !== -1) {
    showFeeError(`第 ${bad + 1} 列沒有填完整（至少勾一個星期、填時段與價格）`);
    return;
  }
  try {
    await api.put(`/api/venues/${feeVenueId}/fee-rates`, items);
  } catch (err) {
    showFeeError("儲存失敗：" + err.message);
    return;
  }
  closeFeeModal();
  await loadVenues();
}

document.addEventListener("DOMContentLoaded", () => {
  loadVenues();
  document.getElementById("btn-fee-add").addEventListener("click", addFeeRow);
  document.getElementById("btn-fee-cancel").addEventListener("click", closeFeeModal);
  document.getElementById("btn-fee-save").addEventListener("click", saveFees);
  document.getElementById("fee-rows").addEventListener("click", (e) => {
    if (e.target.classList.contains("fee-remove")) e.target.closest("tr").remove();
  });
  document.getElementById("btn-add").addEventListener("click", () => openModal(null));
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("venue-form").addEventListener("submit", handleSave);
  document.getElementById("venue-list").addEventListener("click", handleListClick);
  document.getElementById("f-anytime").addEventListener("change", toggleAnytimeFields);
});
