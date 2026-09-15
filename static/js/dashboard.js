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

const SVG_NS = "http://www.w3.org/2000/svg";

function showTooltip(evt, text) {
  const tooltip = document.getElementById("chart-tooltip");
  tooltip.textContent = text;
  tooltip.style.display = "block";
  tooltip.style.left = evt.clientX + 12 + "px";
  tooltip.style.top = evt.clientY + 12 + "px";
}

function hideTooltip() {
  document.getElementById("chart-tooltip").style.display = "none";
}

// 每位學生總學費：水平長條圖，由高到低排列
function renderStudentChart(items, rootId, seriesClass, emptyText) {
  const root = document.getElementById(rootId);
  root.innerHTML = "";
  if (items.length === 0) {
    root.innerHTML = `<p class="chart-empty">${emptyText}</p>`;
    return;
  }

  const barHeight = 20;
  const gap = 10;
  const labelWidth = 110;
  const chartWidth = 560;
  const plotWidth = chartWidth - labelWidth - 70;
  const height = items.length * (barHeight + gap) + gap;
  const maxValue = Math.max(...items.map((i) => i.total_revenue), 1);

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${chartWidth} ${height}`);
  svg.setAttribute("width", "100%");
  svg.style.maxWidth = chartWidth + "px";
  svg.style.height = "auto";
  svg.style.display = "block";

  items.forEach((item, idx) => {
    const y = gap + idx * (barHeight + gap);
    const barLen = Math.max((item.total_revenue / maxValue) * plotWidth, 2);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", labelWidth - 8);
    label.setAttribute("y", y + barHeight / 2 + 4);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("class", "chart-bar-label");
    label.textContent = item.student_name;
    svg.appendChild(label);

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", labelWidth);
    rect.setAttribute("y", y);
    rect.setAttribute("width", barLen);
    rect.setAttribute("height", barHeight);
    rect.setAttribute("rx", 4);
    rect.setAttribute("class", `chart-bar ${seriesClass}`);
    svg.appendChild(rect);

    const value = document.createElementNS(SVG_NS, "text");
    value.setAttribute("x", labelWidth + barLen + 6);
    value.setAttribute("y", y + barHeight / 2 + 4);
    value.setAttribute("class", "chart-value-label");
    value.textContent = Math.round(item.total_revenue).toLocaleString("zh-Hant-TW");
    svg.appendChild(value);

    const hit = document.createElementNS(SVG_NS, "rect");
    hit.setAttribute("x", labelWidth);
    hit.setAttribute("y", y);
    hit.setAttribute("width", barLen);
    hit.setAttribute("height", barHeight);
    hit.setAttribute("class", "chart-bar-hit");
    hit.addEventListener("mousemove", (e) =>
      showTooltip(e, `${item.student_name}：${formatMoney(item.total_revenue)}`)
    );
    hit.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(hit);
  });

  root.appendChild(svg);
}

function renderStudentTable(items, tbodyId, emptyText) {
  const tbody = document.getElementById(tbodyId);
  tbody.innerHTML = "";
  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="2">${emptyText}</td></tr>`;
    return;
  }
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${item.student_name.replace(/</g, "&lt;")}</td><td>${formatMoney(item.total_revenue)}</td>`;
    tbody.appendChild(tr);
  });
}

// 每月學費：直立長條圖，依時間排序
function renderMonthChart(items) {
  const root = document.getElementById("month-chart");
  root.innerHTML = "";
  if (items.length === 0) {
    root.innerHTML = '<p class="chart-empty">目前沒有已收款的紀錄</p>';
    return;
  }

  const barWidth = 24;
  const gap = 24;
  const chartHeight = 220;
  const bottomAxis = 24;
  const topPadding = 20;
  const plotHeight = chartHeight - bottomAxis - topPadding;
  const width = items.length * (barWidth + gap) + gap;
  const maxValue = Math.max(...items.map((i) => i.total_revenue), 1);

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${chartHeight}`);
  svg.setAttribute("width", "100%");
  svg.style.maxWidth = width + "px";
  svg.style.height = "auto";
  svg.style.display = "block";

  const baseline = document.createElementNS(SVG_NS, "line");
  baseline.setAttribute("x1", 0);
  baseline.setAttribute("x2", width);
  baseline.setAttribute("y1", chartHeight - bottomAxis);
  baseline.setAttribute("y2", chartHeight - bottomAxis);
  baseline.setAttribute("class", "chart-gridline");
  svg.appendChild(baseline);

  items.forEach((item, idx) => {
    const x = gap + idx * (barWidth + gap);
    const barLen = Math.max((item.total_revenue / maxValue) * plotHeight, 2);
    const y = chartHeight - bottomAxis - barLen;

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", x);
    rect.setAttribute("y", y);
    rect.setAttribute("width", barWidth);
    rect.setAttribute("height", barLen);
    rect.setAttribute("rx", 4);
    rect.setAttribute("class", "chart-bar");
    svg.appendChild(rect);

    const value = document.createElementNS(SVG_NS, "text");
    value.setAttribute("x", x + barWidth / 2);
    value.setAttribute("y", y - 6);
    value.setAttribute("text-anchor", "middle");
    value.setAttribute("class", "chart-value-label");
    value.textContent = Math.round(item.total_revenue).toLocaleString("zh-Hant-TW");
    svg.appendChild(value);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", x + barWidth / 2);
    label.setAttribute("y", chartHeight - 6);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "chart-bar-label");
    label.textContent = item.month;
    svg.appendChild(label);

    const hit = document.createElementNS(SVG_NS, "rect");
    hit.setAttribute("x", x);
    hit.setAttribute("y", topPadding);
    hit.setAttribute("width", barWidth);
    hit.setAttribute("height", chartHeight - bottomAxis - topPadding);
    hit.setAttribute("class", "chart-bar-hit");
    hit.addEventListener("mousemove", (e) =>
      showTooltip(e, `${item.month}：${formatMoney(item.total_revenue)}`)
    );
    hit.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(hit);
  });

  root.appendChild(svg);
}

function renderMonthTable(items) {
  const tbody = document.getElementById("month-table-body");
  tbody.innerHTML = "";
  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="2">目前沒有已收款的紀錄</td></tr>';
    return;
  }
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${item.month}</td><td>${formatMoney(item.total_revenue)}</td>`;
    tbody.appendChild(tr);
  });
}

async function loadCharts() {
  const [byStudent, byMonth, unpaidByStudent] = await Promise.all([
    api.get("/api/stats/by_student"),
    api.get("/api/stats/by_month"),
    api.get("/api/stats/unpaid_by_student"),
  ]);
  renderStudentChart(byStudent, "student-chart", "", "目前沒有已收款的紀錄");
  renderStudentTable(byStudent, "student-table-body", "目前沒有已收款的紀錄");
  renderMonthChart(byMonth);
  renderMonthTable(byMonth);
  renderStudentChart(unpaidByStudent, "unpaid-chart", "series-2", "目前沒有應收未收的金額");
  renderStudentTable(unpaidByStudent, "unpaid-table-body", "目前沒有應收未收的金額");
}

function handleChartToggle(e) {
  const btn = e.target.closest(".chart-toggle");
  if (!btn) return;
  const targetId = btn.dataset.target;
  const table = document.getElementById(targetId);
  const chartRoot = table.previousElementSibling;
  const showingTable = table.style.display !== "none";
  table.style.display = showingTable ? "none" : "";
  chartRoot.style.display = showingTable ? "" : "none";
  btn.textContent = showingTable ? "表格檢視" : "圖表檢視";
}

document.addEventListener("DOMContentLoaded", () => {
  loadStats();
  loadCharts();
  document.querySelector("main").addEventListener("click", handleChartToggle);
});
