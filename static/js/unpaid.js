// 未收款清單頁邏輯

const ADJ_TYPE_LABEL = {
  headcount_diff: "人數差額",
  venue_fee: "場地費",
  venue_change: "臨時改場地",
  other: "其他",
};

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

let currentAdjustments = [];
let editingAdjustmentId = null;

async function loadUnpaid() {
  const data = await api.get("/api/stats/unpaid");
  renderLessons(data.unpaid_lessons);
  renderPackages(data.unpaid_packages);
  currentAdjustments = data.unsettled_adjustments;
  editingAdjustmentId = null;
  renderAdjustments(currentAdjustments);
}

function renderLessons(lessons) {
  const tbody = document.getElementById("unpaid-lessons");
  tbody.innerHTML = "";
  if (lessons.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">目前沒有未收款課程</td></tr>';
    return;
  }
  lessons.forEach((l) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${l.date} ${l.start_time.slice(0, 5)}</td>
      <td>${escapeHtml(l.student_name)}</td>
      <td>${escapeHtml(l.venue_name)}</td>
      <td>${l.revenue_amount}</td>
      <td><button data-action="pay-lesson" data-id="${l.id}">標記已收款</button></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderPackages(packages) {
  const tbody = document.getElementById("unpaid-packages");
  tbody.innerHTML = "";
  if (packages.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">目前沒有未收款的套組</td></tr>';
    return;
  }
  packages.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.student_name)}</td>
      <td>${escapeHtml(p.name)}</td>
      <td>${p.total_price}</td>
      <td>${p.remaining_sessions} / ${p.total_sessions}</td>
      <td><button data-action="pay-package" data-id="${p.id}">標記已收款</button></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAdjustments(adjustments) {
  const tbody = document.getElementById("unsettled-adjustments");
  tbody.innerHTML = "";
  if (adjustments.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6">目前沒有未結清差額</td></tr>';
    return;
  }
  adjustments.forEach((a) => {
    const tr = document.createElement("tr");
    if (a.id === editingAdjustmentId) {
      const typeOptions = Object.entries(ADJ_TYPE_LABEL)
        .map(
          ([value, label]) =>
            `<option value="${value}" ${value === a.type ? "selected" : ""}>${label}</option>`
        )
        .join("");
      tr.innerHTML = `
        <td>${escapeHtml(a.student_name)}</td>
        <td>${a.lesson_date}</td>
        <td><select id="edit-adj-type">${typeOptions}</select></td>
        <td><input id="edit-adj-amount" type="number" min="0" step="1" value="${a.amount}" /></td>
        <td><input id="edit-adj-note" type="text" value="${escapeHtml(a.note || "")}" /></td>
        <td>
          <button data-action="save-adjustment" data-id="${a.id}">儲存</button>
          <button data-action="cancel-edit-adjustment" class="secondary">取消</button>
          <button data-action="delete-adjustment" class="danger" data-id="${a.id}">刪除</button>
        </td>
      `;
    } else {
      tr.innerHTML = `
        <td>${escapeHtml(a.student_name)}</td>
        <td>${a.lesson_date}</td>
        <td>${ADJ_TYPE_LABEL[a.type] || a.type}</td>
        <td>${a.amount}</td>
        <td>${escapeHtml(a.note || "")}</td>
        <td>
          <button data-action="edit-adjustment" class="secondary" data-id="${a.id}">編輯</button>
          <button data-action="settle-adjustment" data-id="${a.id}">標記結清</button>
        </td>
      `;
    }
    tbody.appendChild(tr);
  });
}

async function handleClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "edit-adjustment") {
    editingAdjustmentId = parseInt(id, 10);
    renderAdjustments(currentAdjustments);
    return;
  }
  if (btn.dataset.action === "cancel-edit-adjustment") {
    editingAdjustmentId = null;
    renderAdjustments(currentAdjustments);
    return;
  }
  try {
    if (btn.dataset.action === "pay-lesson") {
      await api.patch(`/api/lessons/${id}/payment`, { payment_status: "paid" });
    } else if (btn.dataset.action === "pay-package") {
      await api.patch(`/api/packages/${id}/payment`, { payment_status: "paid" });
    } else if (btn.dataset.action === "settle-adjustment") {
      await api.patch(`/api/adjustments/${id}/settle`, {});
    } else if (btn.dataset.action === "save-adjustment") {
      const amount = parseFloat(document.getElementById("edit-adj-amount").value);
      if (Number.isNaN(amount)) {
        alert("請輸入金額");
        return;
      }
      await api.put(`/api/adjustments/${id}`, {
        type: document.getElementById("edit-adj-type").value,
        amount,
        note: document.getElementById("edit-adj-note").value.trim() || null,
      });
    } else if (btn.dataset.action === "delete-adjustment") {
      if (!confirm("確定要刪除這筆差額紀錄嗎？")) return;
      await api.delete(`/api/adjustments/${id}`);
    } else {
      return;
    }
    await loadUnpaid();
  } catch (err) {
    alert("更新失敗：" + err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadUnpaid();
  document.querySelector("main").addEventListener("click", handleClick);
});
