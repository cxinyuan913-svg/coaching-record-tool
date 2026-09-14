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

// 時間選單（24 小時制，僅 00/30 分）：填入時／分兩個 select
// withPlaceholder=true 會加一個未選取的空白選項，用於「新增課程」時強制使用者主動選時間
function populateTimeSelects(hourSelectId, minuteSelectId, withPlaceholder) {
  const hourSelect = document.getElementById(hourSelectId);
  const minuteSelect = document.getElementById(minuteSelectId);
  hourSelect.innerHTML = "";
  minuteSelect.innerHTML = "";
  if (withPlaceholder) {
    const hOpt = document.createElement("option");
    hOpt.value = "";
    hOpt.textContent = "時";
    hourSelect.appendChild(hOpt);
    const mOpt = document.createElement("option");
    mOpt.value = "";
    mOpt.textContent = "分";
    minuteSelect.appendChild(mOpt);
  }
  for (let h = 0; h < 24; h++) {
    const opt = document.createElement("option");
    opt.value = String(h).padStart(2, "0");
    opt.textContent = String(h).padStart(2, "0");
    hourSelect.appendChild(opt);
  }
  ["00", "30"].forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    minuteSelect.appendChild(opt);
  });
}

function setTimeSelectValue(hourSelectId, minuteSelectId, hhmm) {
  const [h, m] = hhmm.split(":");
  document.getElementById(hourSelectId).value = h;
  document.getElementById(minuteSelectId).value = Number(m) >= 30 ? "30" : "00";
}

function getTimeSelectValue(hourSelectId, minuteSelectId) {
  const h = document.getElementById(hourSelectId).value;
  const m = document.getElementById(minuteSelectId).value;
  return h && m ? `${h}:${m}` : "";
}

// 時長選單（小時制，半小時為單位）：0.5 小時 ~ 3 小時，值為分鐘數字串
function minutesToHourLabel(minutes) {
  return `${minutes / 60} 小時`;
}

function populateDurationSelect(selectId, maxMinutes) {
  const select = document.getElementById(selectId);
  select.innerHTML = "";
  for (let m = 30; m <= (maxMinutes || 180); m += 30) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = minutesToHourLabel(m);
    select.appendChild(opt);
  }
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
