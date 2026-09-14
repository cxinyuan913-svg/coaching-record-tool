// 價目表管理頁邏輯

const TIER_LABEL = { new: "新生", friend: "朋友", regular: "熟客" };

let editingId = null;

async function loadRules() {
  const rules = await api.get("/api/price_rules");
  const tbody = document.getElementById("rule-list");
  tbody.innerHTML = "";
  rules.forEach((r) => {
    const headcountLabel =
      r.headcount_min === r.headcount_max
        ? `${r.headcount_min} 人`
        : `${r.headcount_min}-${r.headcount_max} 人`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${headcountLabel}</td>
      <td>${TIER_LABEL[r.tier] || r.tier}</td>
      <td>${r.price}</td>
      <td>
        <button class="secondary" data-action="edit" data-id="${r.id}">編輯</button>
        <button class="danger" data-action="delete" data-id="${r.id}">刪除</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openModal(rule) {
  editingId = rule ? rule.id : null;
  document.getElementById("modal-title").textContent = rule ? "編輯價目規則" : "新增價目規則";
  document.getElementById("f-min").value = rule ? rule.headcount_min : 1;
  document.getElementById("f-max").value = rule ? rule.headcount_max : 1;
  document.getElementById("f-tier").value = rule ? rule.tier : "new";
  document.getElementById("f-price").value = rule ? rule.price : "";
  document.getElementById("rule-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("rule-modal").classList.remove("open");
}

async function handleSave(e) {
  e.preventDefault();
  const payload = {
    headcount_min: parseInt(document.getElementById("f-min").value, 10),
    headcount_max: parseInt(document.getElementById("f-max").value, 10),
    tier: document.getElementById("f-tier").value,
    price: parseFloat(document.getElementById("f-price").value),
  };
  if (payload.headcount_min > payload.headcount_max) {
    alert("人數下限不可大於上限");
    return;
  }
  if (Number.isNaN(payload.price)) {
    alert("請輸入金額");
    return;
  }
  try {
    if (editingId) {
      await api.put(`/api/price_rules/${editingId}`, payload);
    } else {
      await api.post("/api/price_rules", payload);
    }
    closeModal();
    await loadRules();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
}

async function handleListClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "edit") {
    const rule = await api.get(`/api/price_rules/${id}`);
    openModal(rule);
  } else if (btn.dataset.action === "delete") {
    if (confirm("確定要刪除這條價目規則嗎？")) {
      try {
        await api.delete(`/api/price_rules/${id}`);
        await loadRules();
      } catch (err) {
        alert("刪除失敗：" + err.message);
      }
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadRules();
  document.getElementById("btn-add").addEventListener("click", () => openModal(null));
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("rule-form").addEventListener("submit", handleSave);
  document.getElementById("rule-list").addEventListener("click", handleListClick);
});
