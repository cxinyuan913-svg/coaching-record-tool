// 共用 fetch 工具與導覽列 active 狀態標示

// 依「本地時區」格式化成 YYYY-MM-DD；絕對不要用 toISOString().slice(0,10)，
// 那是轉成 UTC 後才截字串，在 UTC+8 會把日期往前拉一天（例如本地 10/6 變成 10/5）
function toLocalDateString(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

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
// withPlaceholder=true 會給「時」加一個未選取的空白選項，強制使用者主動選時間；
// 「分」一律預設 00，選了時之後不用再手動選分鐘
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
  minuteSelect.value = "00";
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
