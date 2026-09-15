// 課程套組管理頁邏輯

const TIER_LABEL = { new: "新生", friend: "朋友", regular: "熟客" };
const WEEKDAY_LABEL = ["週日", "週一", "週二", "週三", "週四", "週五", "週六"];
const STATUS_LABEL = { active: "進行中", completed: "已完成", expired: "已過期" };

let students = [];
let venues = [];
let editingId = null;

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

// 依「第一堂日期」自動推算每週固定上課星期幾，不需要另外詢問
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

// 預估總金額 = (堂課費+場地費)/小時 × 標準時長(小時) × 總堂數，僅供表單即時預覽
function updateEstimatedTotal() {
  const coachFee = parseFloat(document.getElementById("f-coach-fee").value) || 0;
  const venueFee = parseFloat(document.getElementById("f-venue-fee").value) || 0;
  const duration = parseInt(document.getElementById("f-duration").value, 10) || 0;
  const sessions = parseInt(document.getElementById("f-total-sessions").value, 10) || 0;
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
  const isEdit = !!pkg;
  document.getElementById("modal-title").textContent = isEdit ? "編輯套組" : "新增套組（批次排課）";
  document.getElementById("btn-save").textContent = isEdit ? "儲存" : "儲存並批次排課";
  document.getElementById("f-student").disabled = isEdit;
  document.getElementById("row-payment").style.display = isEdit ? "none" : "";
  document.getElementById("edit-note").style.display = isEdit ? "" : "none";

  document.getElementById("f-student").value = pkg ? pkg.student_id : students[0]?.id ?? "";
  document.getElementById("f-venue").value = pkg ? pkg.default_venue_id : venues[0]?.id ?? "";
  document.getElementById("f-name").value = pkg ? pkg.name : "8堂1小時套組";
  document.getElementById("f-duration").value = pkg ? pkg.session_duration : "60";
  document.getElementById("f-total-sessions").value = pkg ? pkg.total_sessions : 8;
  document.getElementById("f-coach-fee").value = pkg ? pkg.coach_fee_per_hour : "";
  document.getElementById("f-venue-fee").value = pkg ? pkg.venue_fee_per_hour : 0;
  document.getElementById("f-purchased-date").value = pkg
    ? pkg.purchased_date
    : new Date().toISOString().slice(0, 10);
  document.getElementById("f-start-date").value = pkg ? pkg.start_date : "";
  setTimeSelectValue(
    "f-recur-time-hour",
    "f-recur-time-minute",
    pkg ? pkg.recur_start_time.slice(0, 5) : "18:00"
  );
  document.getElementById("f-payment").value = "unpaid";
  updateWeekdayHint();
  updateEstimatedTotal();
  document.getElementById("package-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("package-modal").classList.remove("open");
  document.getElementById("f-student").disabled = false;
}

async function handleSave(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById("f-name").value.trim(),
    session_duration: parseInt(document.getElementById("f-duration").value, 10),
    total_sessions: parseInt(document.getElementById("f-total-sessions").value, 10),
    coach_fee_per_hour: parseFloat(document.getElementById("f-coach-fee").value),
    venue_fee_per_hour: parseFloat(document.getElementById("f-venue-fee").value) || 0,
    purchased_date: document.getElementById("f-purchased-date").value,
    start_date: document.getElementById("f-start-date").value,
    recur_weekday: weekdayOfDate(document.getElementById("f-start-date").value),
    recur_start_time: getTimeSelectValue("f-recur-time-hour", "f-recur-time-minute") + ":00",
    default_venue_id: parseInt(document.getElementById("f-venue").value, 10),
  };
  if (
    !payload.name ||
    Number.isNaN(payload.coach_fee_per_hour) ||
    !payload.start_date ||
    !payload.total_sessions ||
    payload.total_sessions < 1
  ) {
    alert("請完整填寫表單（總堂數需至少為 1）");
    return;
  }
  try {
    if (editingId) {
      await api.put(`/api/packages/${editingId}`, payload);
    } else {
      await api.post("/api/packages", {
        ...payload,
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
  document.getElementById("f-start-date").addEventListener("change", updateWeekdayHint);
  document.getElementById("f-coach-fee").addEventListener("input", updateEstimatedTotal);
  document.getElementById("f-venue-fee").addEventListener("input", updateEstimatedTotal);
  document.getElementById("f-duration").addEventListener("change", updateEstimatedTotal);
  document.getElementById("f-total-sessions").addEventListener("input", updateEstimatedTotal);
});
