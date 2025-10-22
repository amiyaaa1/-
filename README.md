# Kiro 账号自动化项目

该项目基于 Python 实现本地化脚本，自动化执行 Kiro 桌面端的登录循环，完成如下操作：

1. 启动 Kiro（`D:\ai translate\Kiro\Kiro.exe`），在登录页选择 Google 或 AWS Builder ID。  
2. 自动打开新的 Chrome 无痕窗口，完成对应的 OAuth/注册表单。  
3. 监听 `C:\Users\ZTX\.aws\sso\cache` 中生成的凭证文件，按照命名约定剪切到 `D:\ai translate\kirofd\gmail`。  
4. 重启 Kiro，回到未登录状态并准备下一轮循环。

## 1. 主要特性
- **模块化设计**：`kiro_automation` 包提供浏览器、邮件、凭证、GUI 操作等独立模块。  
- **配置驱动**：所有路径、登录策略、邮件 API、循环参数均由 `config.toml` 配置。  
- **临时邮箱集成**：内置 ZyraMail API 客户端，自动生成邮箱、轮询验证码。  
- **凭证守护**：使用 `watchdog` 监听 AWS SSO 缓存目录，检测新文件并按规则重命名。  
- **日志统一**：`logger.setup_logging` 输出到终端及可选文件，便于审计与调试。

## 2. 目录结构
```
.
├── README.md
├── config.toml              # 默认配置（运行前请根据实际情况修改）
├── pyproject.toml
└── kiro_automation/
    ├── __init__.py
    ├── __main__.py          # 入口脚本
    ├── auth_url_collector.py
    ├── browser_client.py
    ├── config_manager.py
    ├── credential_handler.py
    ├── email_service.py
    ├── exceptions.py
    ├── generators.py
    ├── kiro_client.py
    └── orchestrator.py
```

## 3. 环境准备
1. **Python**：推荐 Python 3.11（Windows 平台）。  
2. **Chrome & ChromeDriver**：确保 Chrome 与 ChromeDriver 版本匹配，并将 ChromeDriver 路径写入 `config.toml`。  
3. **依赖安装**：
   ```bash
   pip install -e .
   ```
   或使用 `pip install -r requirements.txt`（若更习惯 requirements 管理）。
4. **Windows 自动化权限**：以管理员身份运行终端可减少 pywinauto 操控失败的概率。

## 4. 配置说明
项目根目录提供 `config.toml` 示例，启动前请按需调整：

- `[paths]`
  - `kiro_executable`：Kiro 安装路径。
  - `sso_cache_dir`：AWS SSO 凭证缓存目录。
  - `credential_destination`：凭证移动后的目标目录。若不存在会自动创建。
- `[browser]`
  - `driver_path`、`binary_path`：ChromeDriver 与 Chrome 可执行文件路径。
  - `patterns`：用于识别剪贴板上 OAuth 链接的正则关键词，可按实际域名微调。
- `[google]` 与 `[aws]`
  - Google 配置需提供账号和密码。`enabled=false` 可跳过该策略。  
  - AWS 段配置临时邮箱域名、轮询间隔以及密码长度/字符集。
- `[email_service]`
  - ZyraMail API 信息。敏感值可写成 `env:VARIABLE_NAME`，在运行前以环境变量提供。
- `[loop]`
  - `strategies`：执行策略顺序（如 `"google"`, `"aws"`）。
  - `max_iterations`：限制循环次数，`null` 表示无限循环。
  - `wait_for_credentials`：等待凭证生成的最长秒数。
- `[auth]`
  - 剪贴板轮询频率与超时时间。脚本会等待你复制 Kiro 打开的 OAuth 链接。

> **提示**：运行前可执行 `python -m kiro_automation --config config.toml --help` 查看 CLI 选项。

## 5. 运行方式
```bash
python -m kiro_automation --config path/to/config.toml
```
执行流程：
1. 按配置顺序选择登录策略。  
2. 启动/聚焦 Kiro，点击对应登录按钮。  
3. 脚本监听剪贴板，请在浏览器中新开无痕窗口后复制地址栏 URL；脚本捕获后将自动驱动 Selenium。  
4. Google/AWS 页面自动填写表单、处理验证码。  
5. 新凭证写入 `C:\Users\ZTX\.aws\sso\cache` 时自动重命名并移动。  
6. Kiro 重新启动，进入下一轮。

## 6. 模块速览
| 模块 | 作用 | 关键点 |
| ---- | ---- | ---- |
| `config_manager.py` | 解析 `config.toml`，支持 `env:` 环境变量占位 | 返回 `AppConfig` 数据类，供其他模块直接使用 |
| `logger.py` | 设置统一日志格式与输出目标 | 支持写入文件夹 `logs/automation.log` |
| `kiro_client.py` | 基于 `pywinauto` 启动/操作 Kiro 界面 | 提供 `click_google()` / `click_aws()` |
| `auth_url_collector.py` | 监听剪贴板中的 OAuth 链接 | 默认匹配 `accounts.google.com`、`amazoncognito.com`，可在配置中调整 |
| `browser_client.py` | 使用 Selenium 完成 Google/AWS 流程 | 封装 `GoogleLoginFlow`、`AwsBuilderFlow`，处理表单、验证码及同意页 |
| `email_service.py` | 对接 ZyraMail API | 自动创建邮箱、轮询验证码、解析邮件正文 |
| `credential_handler.py` | `watchdog` 监听 AWS SSO 缓存目录 | 检测新文件稳定后重命名再移动 |
| `generators.py` | 随机生成昵称与密码 | 满足 AWS 密码复杂度要求 |
| `orchestrator.py` | 主循环协调所有模块 | 支持多策略轮换、错误容错、循环间隔 |

## 7. 工作流细节
### 7.1 Google 登录
1. `kiro_client` 点击 “Sign in with Google”。  
2. `ClipboardAuthUrlCollector` 识别你复制的 OAuth 链接。  
3. `GoogleLoginFlow` 自动输入邮箱/密码，处理“我了解”“Continue”等按钮。  
4. Selenium 检测到 “You can close this window” 后退出。  
5. 凭证文件重命名为 `邮箱名+kiro` 并移动。

### 7.2 AWS Builder ID
1. `email_service` 生成临时邮箱，`generators` 创建昵称与密码。  
2. `kiro_client` 点击 “Sign in with AWS Builder ID”。  
3. 捕获 OAuth 链接，`AwsBuilderFlow` 负责填写邮箱、昵称、验证码与密码。  
4. 轮询邮件直到解析出 6 位验证码，完成授权。  
5. 凭证移动时追加随机两位数字：`邮箱名+kiroXX`。

## 8. 调试与常见问题
- **无法捕获 OAuth URL**：确认已复制地址栏链接，或在 `config.toml` 中放宽 `patterns` 正则。  
- **Selenium 找不到元素**：UI 变化时可在 `browser_client.py` 内调整 XPath/CSS 选择器。  
- **凭证未移动**：检查 `wait_for_credentials` 超时时间以及 `watchdog` 权限；可在日志查看是否检测到新文件。  
- **pywinauto 找不到按钮**：使用 `pywinauto.recorder` 检测控件层级，或考虑切换为 `pyautogui` 等图像识别方案。

## 9. 安全与维护建议
- 使用专用 Google 账号/临时邮箱，避免触发主账户风控。  
- `.toml` 中敏感信息请结合 `env:` 与 `.env` 管理，或借助 Windows Credential Manager。  
- 建议开启日志文件，定期备份 `D:\ai translate\kirofd\gmail`。  
- 循环间隔可按实际风控策略调整，必要时在 `orchestrator.py` 中加入失败后指数退避。

## 10. 后续扩展
- 接入 `pyautogui`/`OpenCV` 提升 UI 识别鲁棒性。  
- 在 `email_service` 中支持更多临时邮箱供应商。  
- 将流程封装为 GUI 或 Web 控制台，提供开始/暂停、日志浏览等能力。  
- 编写自动化测试，利用 `pytest` + `responses` 模拟 API 交互。

如需进一步定制，可直接修改相应模块并在 `config.toml` 中扩展配置项。
