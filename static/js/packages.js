// 課程包管理頁邏輯

const TIER_LABEL = { new: "新生", friend: "朋友", regular: "熟客" };
const WEEKDAY_LABEL = ["週日", "週一", "週二", "週三", "週四", "週五", "週六"];
const STATUS_LABEL = { active: "進行中", completed: "已完成", expired: "已過期" };

let students = [];
let venues = [];

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
  const weekdaySelect = document.getElementById("f-weekday");
  weekdaySelect.innerHTML = "";
  WEEKDAY_LABEL.forEach((label, idx) => {
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = label;
    weekdaySelect.appendChild(opt);
  });
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
      <td>${p.session_duration} 分</td>
      <td>${p.remaining_sessions} / ${p.total_sessions}</td>
      <td>${p.price_per_session}</td>
      <td>${STATUS_LABEL[p.status] || p.status}</td>
      <td>
        <button class="secondary" data-action="toggle-payment" data-id="${p.id}" data-current="${p.payment_status}">
          ${p.payment_status === "paid" ? "已收款" : "未收款"}
        </button>
      </td>
      <td>
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

function openModal() {
  document.getElementById("f-student").selectedIndex = 0;
  document.getElementById("f-venue").selectedIndex = 0;
  document.getElementById("f-name").value = "8堂1小時包";
  document.getElementById("f-duration").value = "60";
  document.getElementById("f-total-price").value = "";
  document.getElementById("f-purchased-date").value = new Date().toISOString().slice(0, 10);
  document.getElementById("f-start-date").value = "";
  document.getElementById("f-weekday").value = "1";
  document.getElementById("f-recur-time").value = "18:00";
  document.getElementById("f-payment").value = "unpaid";
  document.getElementById("package-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("package-modal").classList.remove("open");
}

async function handleSave(e) {
  e.preventDefault();
  const payload = {
    student_id: parseInt(document.getElementById("f-student").value, 10),
    name: document.getElementById("f-name").value.trim(),
    session_duration: parseInt(document.getElementById("f-duration").value, 10),
    total_sessions: 8,
    total_price: parseFloat(document.getElementById("f-total-price").value),
    purchased_date: document.getElementById("f-purchased-date").value,
    start_date: document.getElementById("f-start-date").value,
    recur_weekday: parseInt(document.getElementById("f-weekday").value, 10),
    recur_start_time: document.getElementById("f-recur-time").value + ":00",
    default_venue_id: parseInt(document.getElementById("f-venue").value, 10),
    payment_status: document.getElementById("f-payment").value,
  };
  if (!payload.name || Number.isNaN(payload.total_price) || !payload.start_date) {
    alert("請完整填寫表單");
    return;
  }
  try {
    await api.post("/api/packages", payload);
    closeModal();
    await loadPackages();
  } catch (err) {
    alert("儲存失敗：" + err.message);
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
  } else if (btn.dataset.action === "delete") {
    if (confirm("確定要刪除這個包嗎？包底下所有課程也會一併刪除。")) {
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
  document.getElementById("btn-add").addEventListener("click", openModal);
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("package-form").addEventListener("submit", handleSave);
  document.getElementById("package-list").addEventListener("click", handleListClick);
});
