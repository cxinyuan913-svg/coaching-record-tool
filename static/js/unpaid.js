// 未收款清單頁邏輯

const ADJ_TYPE_LABEL = { headcount_diff: "人數差額", venue_fee: "場地費", other: "其他" };

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadUnpaid() {
  const data = await api.get("/api/stats/unpaid");
  renderLessons(data.unpaid_lessons);
  renderPackages(data.unpaid_packages);
  renderAdjustments(data.unsettled_adjustments);
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
    tr.innerHTML = `
      <td>${escapeHtml(a.student_name)}</td>
      <td>${a.lesson_date}</td>
      <td>${ADJ_TYPE_LABEL[a.type] || a.type}</td>
      <td>${a.amount}</td>
      <td>${escapeHtml(a.note || "")}</td>
      <td><button data-action="settle-adjustment" data-id="${a.id}">標記結清</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function handleClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  try {
    if (btn.dataset.action === "pay-lesson") {
      await api.patch(`/api/lessons/${id}/payment`, { payment_status: "paid" });
    } else if (btn.dataset.action === "pay-package") {
      await api.patch(`/api/packages/${id}/payment`, { payment_status: "paid" });
    } else if (btn.dataset.action === "settle-adjustment") {
      await api.patch(`/api/adjustments/${id}/settle`, {});
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
