const healthIndicator = document.querySelector('#health-indicator');
const sandboxesContainer = document.querySelector('#sandboxes');
const cookiesContainer = document.querySelector('#cookies');
const sandboxTemplate = document.querySelector('#sandbox-template');
const cookieTemplate = document.querySelector('#cookie-template');
const createForm = document.querySelector('#create-form');
const refreshBtn = document.querySelector('#refresh-btn');
const refreshCookieBtn = document.querySelector('#refresh-cookie-btn');

async function checkHealth() {
  try {
    const response = await fetch('/api/health');
    if (!response.ok) {
      throw new Error('服务不可用');
    }
    const data = await response.json();
    healthIndicator.textContent = data.status === 'ok' ? '运行正常' : '未知状态';
    healthIndicator.classList.remove('error');
  } catch (error) {
    healthIndicator.textContent = '服务异常';
    healthIndicator.classList.add('error');
  }
}

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || '请求失败');
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function renderLogs(container, logs) {
  container.innerHTML = '';
  if (!logs || logs.length === 0) {
    container.innerHTML = '<p>暂无日志</p>';
    return;
  }
  logs.forEach((item) => {
    const p = document.createElement('p');
    p.textContent = item;
    container.appendChild(p);
  });
}

function renderSandboxCard(data) {
  const node = sandboxTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.id = data.id;
  node.querySelector('[data-field="id"]').textContent = data.id.slice(0, 8);
  node.querySelector('[data-field="account"]').textContent = data.account_email || '未分配';
  node.querySelector('[data-field="target"]').textContent = data.target_url || '未设置';
  node.querySelector('[data-field="status"]').textContent = `状态：${data.status}`;
  node.querySelector('[data-field="message"]').textContent = data.message || '';
  renderLogs(node.querySelector('[data-field="logs"]'), data.logs);
  const cookieField = node.querySelector('[data-field="cookie"]');
  if (data.cookie_file) {
    const link = document.createElement('a');
    link.href = `/api/cookies/${encodeURIComponent(data.cookie_file)}`;
    link.textContent = `下载 Cookie (${data.cookie_file})`;
    link.className = 'primary';
    link.target = '_blank';
    link.rel = 'noopener';
    cookieField.appendChild(link);
  } else {
    cookieField.textContent = '尚未生成 Cookie 文件';
  }
  node.querySelector('[data-action="delete"]').addEventListener('click', async () => {
    if (!confirm('确定要删除该沙箱吗？')) {
      return;
    }
    try {
      await fetchJSON(`/api/sandboxes/${data.id}`, { method: 'DELETE' });
      await refreshSandboxes();
    } catch (error) {
      alert(`删除失败: ${error.message}`);
    }
  });
  return node;
}

function renderCookieCard(data) {
  const node = cookieTemplate.content.firstElementChild.cloneNode(true);
  node.querySelector('[data-field="email"]').textContent = data.email;
  node.querySelector('[data-field="domain"]').textContent = `域名: ${data.domain}`;
  node.querySelector('[data-field="download"]').href = data.url;
  return node;
}

async function refreshSandboxes() {
  try {
    const data = await fetchJSON('/api/sandboxes');
    sandboxesContainer.innerHTML = '';
    if (!data || !data.sandboxes || data.sandboxes.length === 0) {
      sandboxesContainer.innerHTML = '<p>暂无沙箱</p>';
      return;
    }
    data.sandboxes.forEach((sandbox) => {
      sandboxesContainer.appendChild(renderSandboxCard(sandbox));
    });
  } catch (error) {
    sandboxesContainer.innerHTML = `<p class="error">加载失败: ${error.message}</p>`;
  }
}

async function refreshCookies() {
  try {
    const data = await fetchJSON('/api/cookies');
    cookiesContainer.innerHTML = '';
    if (!data || !data.cookies || data.cookies.length === 0) {
      cookiesContainer.innerHTML = '<p>暂无 Cookie 文件</p>';
      return;
    }
    data.cookies.forEach((cookie) => {
      cookiesContainer.appendChild(renderCookieCard(cookie));
    });
  } catch (error) {
    cookiesContainer.innerHTML = `<p class="error">加载失败: ${error.message}</p>`;
  }
}

createForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(createForm);
  const payload = {
    count: Number(formData.get('count')),
    target_url: formData.get('target_url') || null,
    enable_google_login: formData.get('enable_google_login') === 'on',
    auto_site_login: formData.get('auto_site_login') === 'on',
    accounts_blob: formData.get('accounts_blob') || null,
  };

  if (payload.enable_google_login && (!payload.accounts_blob || payload.accounts_blob.trim().length === 0)) {
    alert('启用谷歌登录时必须填写账号信息');
    return;
  }

  try {
    createForm.querySelector('button[type="submit"]').disabled = true;
    await fetchJSON('/api/sandboxes', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    createForm.reset();
    await refreshSandboxes();
    await refreshCookies();
  } catch (error) {
    alert(`创建失败: ${error.message}`);
  } finally {
    createForm.querySelector('button[type="submit"]').disabled = false;
  }
});

refreshBtn.addEventListener('click', async () => {
  await refreshSandboxes();
});

refreshCookieBtn.addEventListener('click', async () => {
  await refreshCookies();
});

checkHealth();
refreshSandboxes();
refreshCookies();
setInterval(checkHealth, 15000);
setInterval(refreshSandboxes, 10000);
setInterval(refreshCookies, 20000);
