// 收入統計頁邏輯

function formatMoney(n) {
  return "NT$ " + Math.round(n).toLocaleString("zh-Hant-TW");
}

async function loadStats() {
  const stats = await api.get("/api/stats/revenue");
  document.getElementById("stat-week").textContent = formatMoney(stats.week);
  document.getElementById("stat-month").textContent = formatMoney(stats.month);
  document.getElementById("stat-year").textContent = formatMoney(stats.year);
  document.getElementById("stat-total").textContent = formatMoney(stats.total);
}

document.addEventListener("DOMContentLoaded", loadStats);
