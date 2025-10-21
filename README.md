# Chrome 沙箱自动化平台

本项目提供一个可视化管理界面，用于批量启动独立的 Chrome 浏览器沙箱、执行谷歌账号登录并自动导出站点 Cookie。前后端均已集成，部署后通过浏览器即可完成所有操作。

## 功能概览

- 🔒 根据输入数量启动完全隔离的浏览器沙箱实例。
- 🌐 支持为每个沙箱指定启动链接。
- 📧 批量解析“邮箱-密码-辅助邮箱”格式的谷歌账号，并自动分配给沙箱。
- 🔁 可选是否执行谷歌登录、以及在目标站点自动触发谷歌账号登录/注册。
- 🍪 任务完成后自动抓取 Cookie 并按“邮箱-域名.txt”命名保存，可在线下载。
- 🖥️ 自带中文 Web 前端，提供启动、状态查看、Cookie 下载等一体化操作体验。

## Windows 部署指南

### 1. 环境准备

1. 安装 [Python 3.10 或更高版本](https://www.python.org/downloads/windows/)，安装时勾选 “Add python.exe to PATH”。
2. 安装 Git（可选，用于获取项目代码）。
3. 确保机器上安装了最新版的 Google Chrome 浏览器。

### 2. 获取代码

```powershell
# 使用 Git 克隆
git clone <你的仓库地址> sandbox-manager
cd sandbox-manager

# 或直接下载压缩包后解压到任意目录
```

### 3. 创建虚拟环境并安装依赖

#### 方式 A：使用 `python -m venv`

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt  # 如未生成 requirements.txt，请参考方式 B
```

> 由于项目使用 `pyproject.toml` 管理依赖，推荐使用下方方式 B。若更习惯 `pip`，可以执行 `pip install fastapi uvicorn[standard] selenium webdriver-manager jinja2 python-multipart` 安装依赖。

#### 方式 B：使用 Poetry（推荐）

1. 安装 [Poetry](https://python-poetry.org/docs/#installation)。
2. 在项目根目录执行：

   ```powershell
   poetry install
   ```

> 本项目改为使用 Selenium + webdriver-manager 驱动 Chrome，首次运行时会自动下载匹配的 ChromeDriver，无需额外安装 Microsoft Visual C++ 组件。

### 4. 启动服务

```powershell
# 若使用 Poetry
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 若使用纯 pip/venv
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后，在浏览器访问 `http://127.0.0.1:8000/` 即可进入前端界面。

## 使用说明

1. **沙箱数量**：输入需要同时启动的浏览器实例数量。
2. **默认打开链接**：所有沙箱在完成登录后都会访问该链接。
3. **谷歌账号批量输入**：
   - 每行代表一个账号，支持常见的 `账号-密码-辅助邮箱`、`账号;密码;辅助邮箱` 等格式。
   - 系统会自动识别邮箱、密码与辅助邮箱，并分配给对应的沙箱。
4. **启用谷歌账号自动登录**：勾选后会在沙箱启动时先登录谷歌。
5. **登录目标站点时尝试使用谷歌账号注册/登录**：若目标站点存在 “Google 登录/注册” 按钮，系统会自动点击并使用已登录的谷歌账号完成站点认证。
6. **使用无头模式运行浏览器**：勾选后浏览器不会显示界面，适合服务器环境。
7. 点击“启动沙箱”后，可在下方表格实时查看任务状态，并下载对应的 Cookie 文件。

## 常见问题

- **无法自动登录谷歌**：谷歌可能触发安全验证或 2FA，请确认账号安全设置允许自动化登录，必要时在本地浏览器提前信任设备。
- **站点未能识别到谷歌登录按钮**：不同站点前端实现差异较大，若自动点击失败，可在沙箱启动后手动处理。
- **ChromeDriver 下载失败**：请确认网络可以访问 `chromedriver.storage.googleapis.com`，或提前在离线环境手动下载驱动并放置到 `PATH` 中。

## 开发与扩展

- 主要业务逻辑位于 `app/sandbox_manager.py`。
- Web API 入口为 `app/main.py`，前端静态资源位于 `app/static/` 和 `app/templates/`。
- 可根据需要扩展更多沙箱控制接口，例如停止任务、实时截图等。

## 许可证

本项目示例仅用于演示用途，可根据实际需求自由修改与扩展。
