const form = document.getElementById("launch-form");
const refreshBtn = document.getElementById("refresh-btn");
const tableBody = document.getElementById("sandbox-table-body");

async function fetchStatus() {
  const response = await fetch("/api/sandboxes");
  if (!response.ok) {
    console.error("获取沙箱状态失败");
    return;
  }
  const data = await response.json();
  renderTable(data.items || []);
}

function renderTable(items) {
  tableBody.innerHTML = "";
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "暂无沙箱任务";
    row.appendChild(cell);
    tableBody.appendChild(row);
    return;
  }
  for (const item of items) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><code>${item.id}</code></td>
      <td>${item.email ?? "-"}</td>
      <td><a href="${item.start_url}" target="_blank" rel="noopener">访问链接</a></td>
      <td>${item.domain ?? "-"}</td>
      <td>${translateState(item.state)}</td>
      <td>${item.message ?? ""}</td>
      <td>${item.cookie_ready && item.download_url ? `<a href="${item.download_url}">下载</a>` : "-"}</td>
    `;
    tableBody.appendChild(row);
  }
}

function translateState(state) {
  switch (state) {
    case "pending":
      return "等待中";
    case "running":
      return "运行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return state;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = {
    count: Number(formData.get("count")),
    start_url: formData.get("start_url"),
    accounts_raw: formData.get("accounts_raw") || "",
    enable_google_login: formData.get("enable_google_login") === "on",
    enable_site_google_registration: formData.get("enable_site_google_registration") === "on",
    headless: formData.get("headless") === "on",
  };

  const response = await fetch("/api/sandboxes/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message = detail?.detail ?? "启动失败";
    alert(message);
    return;
  }

  form.reset();
  await fetchStatus();
});

refreshBtn.addEventListener("click", fetchStatus);

setInterval(fetchStatus, 5000);
fetchStatus();
