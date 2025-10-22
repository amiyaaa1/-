# Chrome Sandbox Manager

该项目提供了一个在 Windows 上运行的 Python 脚本，用于批量创建真正隔离的一次性 Chrome 用户目录，并在关闭所有窗口后自动清理本次创建的目录。脚本支持自动打开指定链接、在会话过程中导出特定站点的全部 Cookie，并在清理前给出确认提示以防误删。

## 功能概览
- 为每个窗口生成独立的临时用户目录并记录本次会话所创建的所有目录。
- 监控当前会话中启动的 Chrome 进程，确认全部退出后提示是否清理目录（默认清理）。
- 支持在启动时为每个窗口自动打开指定网址。
- 会话运行过程中，可随时输入 `cookie <网址>` 指令导出该域名的全部 Cookie，文件将存储在 `config.json` 中配置的目录，文件名形如 `example.com_1234.txt`。
- 自动处理 Chrome 新版的 Cookie 加密（需要 Windows DPAPI 和 AES-GCM 解密）。

## 环境准备
1. 安装 [Python 3.10+](https://www.python.org/downloads/)（确保在安装时勾选“Add Python to PATH”）。
2. 安装项目依赖：
   ```powershell
   pip install -r requirements.txt
   ```
3. 安装 Google Chrome，并确认其可执行文件路径。

## 配置文件
首次运行前，请复制 `config.example.json` 为 `config.json` 并根据需要修改：

```json
{
  "chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "use_incognito": false,
  "default_urls": [
    "https://www.google.com"
  ],
  "cookie_output_dir": "D:\\ai translate\\cookie"
}
```

- `chrome_path`：Chrome 可执行文件路径（必须根据你的实际安装位置修改）。
- `use_incognito`：是否使用无痕模式。**注意：无痕模式下不会持久化 Cookie，因而无法导出 Cookie。** 如果需要导出 Cookie，请保持为 `false`。
- `default_urls`：启动每个 Chrome 窗口时自动打开的链接列表，可为空数组。
- `cookie_output_dir`：保存导出 Cookie 文件的目标目录。脚本会自动创建该目录，但你需要确认目标盘符存在且具有写入权限。

## 使用说明
1. 在项目根目录打开命令提示符或 PowerShell。
2. 运行脚本：
   ```powershell
   python sandbox_manager.py
   ```
3. 按提示输入需要打开的窗口数量。脚本会为每个窗口生成一个独立的临时配置目录，并记录在 `session_dirs.json` 中。
4. 在 Chrome 运行期间，可在脚本控制台输入以下指令：
   - `cookie <网址>`：从所有临时目录中读取该域名相关的 Cookie，并写入配置中指定的目录。例：`cookie https://example.com`。
   - `help`：查看可用指令。
   - `exit`：在 Chrome 未全部关闭时终止脚本的交互模式（不会强制关闭 Chrome）。
5. 当所有会话中的 Chrome 窗口关闭后，脚本会提示是否删除本次创建的临时目录。输入 `y`（默认）则立即清理；输入 `n` 可保留目录供手动检查。

## 其它说明
- Cookie 导出文件使用 UTF-8 编码，以 JSON 形式保存完整字段（名称、值、域、路径、过期时间、Secure / HttpOnly 等）。文件名采用域名加四位随机数字，防止覆盖。
- 如果需要长期保留某次会话的数据，可在清理提示时选择 `n`。记录的目录列表可在 `session_dirs.json` 中查看。
- 如需再次运行，只需重新执行脚本即可，会生成新的独立会话目录并自动管理清理流程。

## 疑难排查
- 如果脚本无法找到 Chrome，请重新检查 `config.json` 中的 `chrome_path`。
- 若导出 Cookie 时报错，请确保已访问目标站点且未启用无痕模式，并确认 `cookie_output_dir` 可写。
- 若提示缺少依赖，请重新执行 `pip install -r requirements.txt`。
