const form = document.getElementById('create-form');
const statusLabel = document.getElementById('create-status');
const tableBody = document.querySelector('#sandbox-table tbody');
const refreshBtn = document.getElementById('refresh-btn');
const googleLoginCheckbox = document.getElementById('google-login');
const siteLoginCheckbox = document.getElementById('site-login');

async function fetchSandboxes() {
  try {
    const res = await fetch('/api/sandboxes');
    if (!res.ok) {
      throw new Error('无法获取沙箱列表');
    }
    const data = await res.json();
    renderSandboxes(data.sandboxes || []);
  } catch (err) {
    console.error(err);
    statusLabel.textContent = `获取沙箱列表失败：${err.message}`;
  }
}

function renderSandboxes(sandboxes) {
  tableBody.innerHTML = '';
  if (!sandboxes.length) {
    const emptyRow = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.textContent = '暂无沙箱';
    emptyRow.appendChild(td);
    tableBody.appendChild(emptyRow);
    return;
  }

  sandboxes.forEach((sandbox) => {
    const row = document.createElement('tr');

    const idCell = document.createElement('td');
    idCell.classList.add('mono');
    idCell.textContent = sandbox.id;
    row.appendChild(idCell);

    const emailCell = document.createElement('td');
    emailCell.textContent = sandbox.email || '-';
    row.appendChild(emailCell);

    const statusCell = document.createElement('td');
    statusCell.textContent = sandbox.status;
    row.appendChild(statusCell);

    const urlCell = document.createElement('td');
    urlCell.textContent = sandbox.default_url;
    row.appendChild(urlCell);

    const cookieCell = document.createElement('td');
    if (sandbox.cookie_file) {
      const link = document.createElement('a');
      link.href = `/api/sandboxes/${sandbox.id}/cookie`;
      link.textContent = sandbox.cookie_file;
      link.setAttribute('download', sandbox.cookie_file);
      cookieCell.appendChild(link);
    } else {
      cookieCell.textContent = '-';
    }
    row.appendChild(cookieCell);

    const actionCell = document.createElement('td');
    actionCell.classList.add('actions');

    const logButton = document.createElement('button');
    logButton.classList.add('secondary');
    logButton.textContent = '查看日志';
    logButton.addEventListener('click', () => showLogs(sandbox.id));
    actionCell.appendChild(logButton);

    const deleteButton = document.createElement('button');
    deleteButton.classList.add('danger');
    deleteButton.textContent = '删除';
    deleteButton.addEventListener('click', () => deleteSandbox(sandbox.id));
    actionCell.appendChild(deleteButton);

    row.appendChild(actionCell);
    tableBody.appendChild(row);
  });
}

async function createSandboxes(event) {
  event.preventDefault();
  statusLabel.textContent = '正在创建沙箱...';
  const formData = new FormData(form);
  const payload = {
    count: Number(formData.get('count')),
    default_url: formData.get('default_url'),
    google_login: formData.get('google_login') === 'on',
    auto_site_login: formData.get('auto_site_login') === 'on',
    accounts: formData.get('accounts'),
  };

  try {
    const res = await fetch('/api/sandboxes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || '创建沙箱失败');
    }
    statusLabel.textContent = '沙箱创建任务已提交';
    form.reset();
    document.getElementById('google-login').checked = payload.google_login;
    document.getElementById('site-login').checked = payload.auto_site_login;
    syncSiteLoginState();
    await fetchSandboxes();
  } catch (err) {
    statusLabel.textContent = `创建失败：${err.message}`;
  }
}

async function deleteSandbox(id) {
  if (!confirm('确定要删除该沙箱吗？')) {
    return;
  }
  try {
    const res = await fetch(`/api/sandboxes/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      throw new Error('删除沙箱失败');
    }
    await fetchSandboxes();
  } catch (err) {
    alert(err.message);
  }
}

async function showLogs(id) {
  try {
    const res = await fetch(`/api/sandboxes/${id}/logs`);
    if (!res.ok) {
      throw new Error('无法获取日志');
    }
    const data = await res.json();
    const logText = (data.log || []).join('\n');
    alert(logText || '暂无日志');
  } catch (err) {
    alert(err.message);
  }
}

form.addEventListener('submit', createSandboxes);
refreshBtn.addEventListener('click', fetchSandboxes);
googleLoginCheckbox.addEventListener('change', syncSiteLoginState);

function syncSiteLoginState() {
  if (!googleLoginCheckbox.checked) {
    siteLoginCheckbox.checked = false;
    siteLoginCheckbox.disabled = true;
  } else {
    siteLoginCheckbox.disabled = false;
  }
}

setInterval(fetchSandboxes, 5000);
fetchSandboxes();
syncSiteLoginState();
