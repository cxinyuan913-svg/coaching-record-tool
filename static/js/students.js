// 學生管理頁邏輯

const TIER_LABEL = { new: "新生", friend: "朋友", regular: "熟客" };

let editingId = null;

async function loadStudents() {
  const [students, packages] = await Promise.all([
    api.get("/api/students"),
    api.get("/api/packages?status=active"),
  ]);
  const packagesByStudent = {};
  packages.forEach((p) => {
    (packagesByStudent[p.student_id] = packagesByStudent[p.student_id] || []).push(p);
  });

  // 有進行中套組（有約課）的學生排前面，沒約課的排後面；同一組內維持原本順序
  const sortedStudents = [...students].sort((a, b) => {
    const aHasPkg = (packagesByStudent[a.id] || []).length > 0;
    const bHasPkg = (packagesByStudent[b.id] || []).length > 0;
    return (bHasPkg ? 1 : 0) - (aHasPkg ? 1 : 0);
  });

  const tbody = document.getElementById("student-list");
  tbody.innerHTML = "";
  sortedStudents.forEach((s) => {
    const pkgs = packagesByStudent[s.id] || [];
    const pkgSummary = pkgs
      .map((p) => `${escapeHtml(p.name)}（${p.remaining_sessions}/${p.total_sessions}）`)
      .join("、");
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(s.contact || "")}</td>
      <td>${TIER_LABEL[s.tier] || s.tier}</td>
      <td>${pkgSummary || "—"}</td>
      <td>${escapeHtml(s.note || "")}</td>
      <td>
        <button class="secondary" data-action="edit" data-id="${s.id}">編輯</button>
        <button class="danger" data-action="delete" data-id="${s.id}">刪除</button>
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

function openModal(student) {
  editingId = student ? student.id : null;
  document.getElementById("modal-title").textContent = student ? "編輯學生" : "新增學生";
  document.getElementById("f-name").value = student ? student.name : "";
  document.getElementById("f-contact").value = student ? student.contact || "" : "";
  document.getElementById("f-tier").value = student ? student.tier : "new";
  document.getElementById("f-note").value = student ? student.note || "" : "";
  document.getElementById("student-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("student-modal").classList.remove("open");
}

async function handleSave(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById("f-name").value.trim(),
    contact: document.getElementById("f-contact").value.trim() || null,
    tier: document.getElementById("f-tier").value,
    note: document.getElementById("f-note").value.trim() || null,
  };
  if (!payload.name) {
    alert("請輸入姓名");
    return;
  }
  try {
    if (editingId) {
      await api.put(`/api/students/${editingId}`, payload);
    } else {
      await api.post("/api/students", payload);
    }
    closeModal();
    await loadStudents();
  } catch (err) {
    alert("儲存失敗：" + err.message);
  }
}

async function handleListClick(e) {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "edit") {
    const student = await api.get(`/api/students/${id}`);
    openModal(student);
  } else if (btn.dataset.action === "delete") {
    if (await confirmDialog("確定要刪除這位學生嗎？")) {
      try {
        await api.delete(`/api/students/${id}`);
        await loadStudents();
      } catch (err) {
        alert("刪除失敗：" + err.message);
      }
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadStudents();
  document.getElementById("btn-add").addEventListener("click", () => openModal(null));
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("student-form").addEventListener("submit", handleSave);
  document.getElementById("student-list").addEventListener("click", handleListClick);
});
