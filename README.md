# Chrome 浏览器沙箱自动化平台

该项目提供一个可视化平台，能够批量创建完全隔离的 Chrome 浏览器沙箱，自动执行谷歌账号登录、站点内的 Google 登录操作，并在完成后导出登录后的 Cookie 文件。后端基于 Express + Puppeteer（复用本机 Chrome/Edge 浏览器），无需额外安装 Microsoft Visual C++ 运行库。

## 功能特性

- ✅ 根据输入的数量创建多个独立的浏览器沙箱，每个沙箱使用专属用户数据目录，互不影响。
- ✅ 支持在启动时为每个沙箱指定默认打开的网址。
- ✅ 可批量导入谷歌账号（邮箱-密码-辅助邮箱），系统会自动解析格式，并在启用时执行谷歌登录。
- ✅ 可选择是否在进入目标网站后自动尝试“Google Login/谷歌登录”按钮，实现站点账号注册或登录。
- ✅ 前端页面集中提供沙箱创建、状态监控、Cookie 下载与沙箱删除操作。
- ✅ 登录完成后自动抓取目标站点 Cookie，以“邮箱-域名.txt”命名并保存在服务器 `server/data/cookies` 目录，同时提供下载链接。

## 目录结构

```
- client/         # Vite + React 前端
- server/         # Express + Puppeteer 后端
- data/           # 运行时自动生成的沙箱数据与 Cookie（默认忽略提交）
```

## Windows 部署与运行

### 1. 环境准备

1. 安装 [Node.js 18+](https://nodejs.org/)（建议使用 LTS 版本）。
2. 克隆或下载本项目代码，并在 PowerShell 或 CMD 中进入项目根目录。
3. 运行以下命令安装依赖：

   ```powershell
   npm run install:all
   ```

4. 确保系统中已经安装了 Chrome 或 Microsoft Edge 浏览器（64 位版本优先）。若浏览器位于非默认目录，可在启动前设置环境变量 `CHROME_EXECUTABLE` 指向浏览器可执行文件，例如：

   ```powershell
   $env:CHROME_EXECUTABLE="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
   ```

   （在 PowerShell 会话中设置后即可直接运行，或写入系统环境变量以便长期生效。）

### 2. 开发模式启动

```powershell
npm run dev
```

- 前端开发服务器默认运行在 <http://localhost:5173>
- 后端 API 运行在 <http://localhost:4000>
- 前端会通过代理访问后端，浏览器页面加载后即可开始操作。

### 3. 生产模式构建与启动

```powershell
npm run build       # 构建前端
npm run start       # 仅启动后端，自动托管 client/dist 中的静态文件
```

此时访问 <http://localhost:4000> 即可进入控制台。

### 4. 使用流程

1. 打开控制台，填写要创建的沙箱数量、默认链接、账号列表，并勾选所需的自动化选项。
2. 账号输入示例：
   ```
   user1@example.com-Password123-recovery@example.com
   user2@mydomain.com;Pass!word2;help@another.com
   ```
   系统会自动识别分隔符并提取邮箱 / 密码 / 辅助邮箱。
3. 点击“创建沙箱”，稍候即可在下方列表看到每个沙箱的状态及最新访问的页面。
4. 若启用了谷歌登录和站点自动登录，流程结束后可以直接点击“下载 Cookie”获取对应的 txt 文件。
5. 通过“删除”按钮可随时关闭并移除某个沙箱。

> ⚠️ **提示**：谷歌账号可能触发安全验证（如短信、二次验证或验证码），此时自动化流程会中断，需要人工介入。

## 重要说明

- Puppeteer 会以有界面模式启动本机的 Chrome/Edge。确保系统允许弹出浏览器窗口，并提前关闭可能的弹窗拦截或杀毒提示。
- 每个沙箱会在 `server/data/sessions` 下创建专属的用户数据目录，删除沙箱或停止服务时建议手动清理。
- 由于目标网站登录逻辑复杂多样，自动识别 Google 登录按钮采用启发式方法，无法保证 100% 成功，可在站点内手动辅助。

## 常见命令

| 命令 | 说明 |
| --- | --- |
| `npm run install:all` | 安装前后端依赖 |
| `npm run dev` | 前后端同时启动（开发模式） |
| `npm run build` | 构建前端静态文件 |
| `npm run start` | 在生产模式下仅启动后端 |

## 许可

本项目代码以 MIT 许可发布，可自由修改和扩展。欢迎根据业务需要自行二次开发。
