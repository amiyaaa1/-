import { useCallback, useEffect, useMemo, useState } from 'react';

const STATUS_TEXT = {
  initializing: '初始化中',
  running: '运行中',
  error: '出现错误',
  stopped: '已关闭'
};

const statusClass = (status) => `status-pill ${status ?? 'initializing'}`;

export default function App() {
  const [count, setCount] = useState(1);
  const [defaultUrl, setDefaultUrl] = useState('https://');
  const [rawAccounts, setRawAccounts] = useState('');
  const [useGoogleLogin, setUseGoogleLogin] = useState(true);
  const [enableSiteAutomation, setEnableSiteAutomation] = useState(true);
  const [sandboxes, setSandboxes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const parsedAccounts = useMemo(() => {
    return rawAccounts
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(/[;|,\t]/).map((chunk) => chunk.trim());
        if (parts.length >= 3) {
          return {
            email: parts[0],
            password: parts[1],
            recoveryEmail: parts[2]
          };
        }
        const dashParts = line.split(/\s*-\s*/).map((chunk) => chunk.trim());
        if (dashParts.length >= 3) {
          return {
            email: dashParts[0],
            password: dashParts[1],
            recoveryEmail: dashParts[2]
          };
        }
        return null;
      })
      .filter(Boolean);
  }, [rawAccounts]);

  const fetchSandboxes = useCallback(async () => {
    try {
      const res = await fetch('/api/sandboxes');
      if (!res.ok) {
        throw new Error('无法获取沙箱列表');
      }
      const data = await res.json();
      setSandboxes(data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    fetchSandboxes();
    const timer = setInterval(fetchSandboxes, 4000);
    return () => clearInterval(timer);
  }, [fetchSandboxes]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = {
        count: Number(count) || 1,
        defaultUrl,
        useGoogleLogin,
        enableSiteAutomation,
        accounts: parsedAccounts
      };
      const res = await fetch('/api/sandboxes', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const message = await res.text();
        throw new Error(message || '创建沙箱失败');
      }
      await fetchSandboxes();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('确认删除该沙箱？')) {
      return;
    }
    try {
      const res = await fetch(`/api/sandboxes/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        throw new Error('删除沙箱失败');
      }
      await fetchSandboxes();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="container">
      <header>
        <h1>Chrome 沙箱自动化平台</h1>
        <p>批量创建独立浏览器沙箱、自动完成谷歌登录、站点登录以及 Cookie 抓取。</p>
      </header>

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="count">沙箱数量</label>
            <input
              id="count"
              type="number"
              min="1"
              value={count}
              onChange={(event) => setCount(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="url">默认打开的链接</label>
            <input
              id="url"
              type="text"
              value={defaultUrl}
              onChange={(event) => setDefaultUrl(event.target.value)}
              placeholder="例如：https://example.com/login"
            />
          </div>

          <div className="field">
            <label htmlFor="accounts">谷歌账号列表</label>
            <textarea
              id="accounts"
              value={rawAccounts}
              onChange={(event) => setRawAccounts(event.target.value)}
              placeholder={'每行一个账号，支持格式：\naccount@example.com-密码-辅助邮箱\naccount@example.com;密码;辅助邮箱'}
            />
            <p className="hint">
              <strong>识别规则：</strong> 系统会自动分析分隔符（- ; , 或制表符），按“邮箱-密码-辅助邮箱”顺序提取信息。如果沙箱数量大于账号数，将循环复用账号。
            </p>
          </div>

          <div className="field toggle">
            <input
              id="useGoogleLogin"
              type="checkbox"
              checked={useGoogleLogin}
              onChange={(event) => setUseGoogleLogin(event.target.checked)}
            />
            <label htmlFor="useGoogleLogin">启用谷歌账号自动登录</label>
          </div>

          <div className="field toggle">
            <input
              id="enableSiteAutomation"
              type="checkbox"
              checked={enableSiteAutomation}
              onChange={(event) => setEnableSiteAutomation(event.target.checked)}
            />
            <label htmlFor="enableSiteAutomation">登录后自动尝试在默认站点执行谷歌快速登录</label>
          </div>

          {error && <div className="error-message">{error}</div>}

          <div className="actions">
            <button className="primary" type="submit" disabled={loading}>
              {loading ? '正在创建…' : '创建沙箱'}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setRawAccounts('');
                setError('');
              }}
            >
              清空账号列表
            </button>
          </div>
        </form>
      </div>

      <div className="card">
        <h2>沙箱列表</h2>
        <p className="hint">
          沙箱启动后会自动在后台运行。若启用了谷歌登录与站点登录，流程完成后会在服务器 <code>downloads</code> 目录下生成 Cookie 文本，可通过“下载 Cookie”按钮获取。
        </p>
        <table className="sandboxes-list">
          <thead>
            <tr>
              <th>ID</th>
              <th>状态</th>
              <th>谷歌账号</th>
              <th>当前页面</th>
              <th>默认链接</th>
              <th>Cookie 文件</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sandboxes.length === 0 && (
              <tr>
                <td colSpan={7}>暂无沙箱，请先创建。</td>
              </tr>
            )}
            {sandboxes.map((sandbox) => (
              <tr key={sandbox.id}>
                <td>{sandbox.id}</td>
                <td>
                  <span className={statusClass(sandbox.status)}>
                    {STATUS_TEXT[sandbox.status] ?? sandbox.status}
                  </span>
                  {sandbox.error && <div className="error-message">{sandbox.error}</div>}
                </td>
                <td>{sandbox.account?.email ?? '未分配'}</td>
                <td>{sandbox.currentUrl ?? '—'}</td>
                <td>{sandbox.defaultUrl}</td>
                <td>
                  {sandbox.cookieFile ? (
                    <a href={`/downloads/${encodeURIComponent(sandbox.cookieFile)}`} download>
                      下载 Cookie
                    </a>
                  ) : (
                    '未生成'
                  )}
                </td>
                <td>
                  <button className="secondary" onClick={() => handleDelete(sandbox.id)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
