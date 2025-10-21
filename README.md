# Chrome 沙箱自动化平台

本项目提供一个基于 FastAPI + Selenium 的可视化平台，可以批量启动相互隔离的 Chrome 浏览器沙箱，自动完成谷歌登录、站点谷歌登录识别以及 Cookie 抓取，并提供前端页面统一管理。整个方案直接调用系统中的 Google Chrome（或自定义路径的便携版），无需安装 Microsoft Visual C++ 运行库即可使用。

## 功能概览

- 🌀 按数量创建互相隔离的浏览器沙箱（每个沙箱拥有独立的用户数据目录）。
- 🔗 启动时可指定默认打开的网页链接。
- 🔐 支持批量导入谷歌账号（邮箱-密码-辅助邮箱），并在沙箱启动时自动执行谷歌登录。
- 🤖 可选在目标站点自动识别登录/注册入口并尝试使用谷歌账号完成站点登录。
- 🍪 登录完成后自动保存目标站点 Cookie 到本地文本文件（命名格式：`邮箱-域名.txt`）。
- 🗑️ 前端页面可查看沙箱状态、日志并随时删除沙箱。
- 🖥️ 提供整合前端，可在浏览器中完成全部操作。

## Windows 部署指南

以下步骤基于 Windows 10/11，使用 PowerShell 或命令提示符执行。

### 1. 安装依赖

1. 安装 [Python 3.10+](https://www.python.org/downloads/)，并在安装向导中勾选 “Add Python to PATH”。
2. 安装或准备好可执行的 Google Chrome（支持便携版）。若使用便携版，可通过环境变量告知项目可执行文件路径。
3. （可选）安装 [Git](https://git-scm.com/download/win) 以便克隆仓库。

```powershell
# 克隆仓库（或直接下载压缩包解压）
git clone https://<your-repo-url>.git
cd <your-repo-folder>

# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 安装后端依赖（无需 Microsoft Visual C++）
pip install -r requirements.txt

# （可选）设置便携版 Chrome 路径，仅当前终端有效
$env:SANDBOX_CHROME_BINARY = 'D:\\tools\\chrome-win\\chrome.exe'
```

> **提示**：Selenium 会自动下载匹配版本的 ChromeDriver，只需保证 Chrome 可执行文件可用。如需手动指定 Chrome 路径，请设置 `SANDBOX_CHROME_BINARY` 环境变量。

### 2. 启动服务

```powershell
# 仍然在虚拟环境中执行
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后，终端会显示 `Uvicorn running on http://127.0.0.1:8000`。在浏览器访问该地址即可打开前端页面。

### 3. 前端使用说明

1. 在 “创建沙箱” 面板中输入要启动的沙箱数量以及默认访问的链接。
2. 勾选 “启用谷歌账号自动登录” 时，需在下方文本框粘贴账号信息。
   - 每行一个账号，顺序固定为：`谷歌邮箱-密码-辅助邮箱` 或 `谷歌邮箱;密码;辅助邮箱`。
   - 账号后缀不一定是 `gmail.com`，系统会自动识别。
3. 勾选 “目标站点启用谷歌注册/登录识别” 后，沙箱会在打开目标链接后自动侦测页面中的登录/注册入口，尝试使用已登录的谷歌账号完成站点登录。
4. 点击“启动沙箱”后，可在右侧“沙箱列表”中查看每个沙箱的实时状态与日志，并支持随时删除。
5. 登录完成后生成的 Cookie 文件会显示在“Cookie 文件”面板，可直接下载。

### 4. 关键目录

- `data/profiles/`：沙箱用户数据目录，每个沙箱独立。
- `data/cookies/`：抓取到的 Cookie 文本文件。
- `frontend/`：前端页面资源，可自行美化或扩展。

### 5. 常见问题

- **浏览器未显示？** 默认以无头模式启动 Chrome。如需查看真实窗口，可设置环境变量 `SANDBOX_HEADLESS=false` 并确保系统具备图形界面。
- **谷歌登录失败？** 谷歌对于自动化登录可能触发风控，建议准备备用账号、开启辅助邮箱，并根据日志定位问题。
- **Cookie 文件为空？** 确保目标站点在登录完成后已跳转到登录后的页面，系统会在网络空闲后再保存 Cookie。

## 项目结构

```
app/              # 后端主代码
frontend/         # 前端静态资源
requirements.txt  # Python 依赖
README.md         # 使用说明（当前文件）
data/             # 沙箱数据 & Cookie 输出目录
```

## 开发建议

- 如需自定义沙箱逻辑，可在 `app/sandbox.py` 中扩展流程。
- 若要增加更多前端交互，可编辑 `frontend/app.js` 与 `frontend/styles.css`。
- 生产环境建议在 `uvicorn` 前使用 `gunicorn` 或 `hypercorn` 搭配 `--workers` 运行。

祝使用愉快！
