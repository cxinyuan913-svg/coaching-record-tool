// 共用 fetch 工具與導覽列 active 狀態標示

async function apiRequest(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch (e) {
      // 忽略非 JSON 錯誤內容
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

const api = {
  get: (url) => apiRequest("GET", url),
  post: (url, body) => apiRequest("POST", url, body),
  put: (url, body) => apiRequest("PUT", url, body),
  patch: (url, body) => apiRequest("PATCH", url, body),
  delete: (url) => apiRequest("DELETE", url),
};

// 將 "HH:MM" 時間字串校正到最近的整點或半點（例如 18:12 -> 18:00、18:16 -> 18:30）
function roundToHalfHour(timeStr) {
  const [h, m] = timeStr.split(":").map(Number);
  let totalMinutes = h * 60 + Math.round(m / 30) * 30;
  totalMinutes = ((totalMinutes % 1440) + 1440) % 1440; // 避免超過 23:30 進位跨日
  const rh = Math.floor(totalMinutes / 60);
  const rm = totalMinutes % 60;
  return `${String(rh).padStart(2, "0")}:${String(rm).padStart(2, "0")}`;
}

function highlightActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll("nav.topnav a").forEach((a) => {
    if (a.getAttribute("href") === path) {
      a.classList.add("active");
    }
  });
}

document.addEventListener("DOMContentLoaded", highlightActiveNav);
