@echo off
REM 强制控制台使用 UTF-8，避免中文乱码
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM ====== 配置区域 ======
REM Chrome 路径（与实际不符请改）
set "chrome_path=C:\Program Files\Google\Chrome\Application\chrome.exe"

REM 是否使用无痕模式（1=启用，0=禁用）
set "USE_INCOGNITO=1"

REM 使用分号分隔的待自动打开链接（含特殊字符时需转义），或留空改用外部文件
set "AUTO_OPEN_URLS="

REM 可选：放置链接列表的文本文件（每行一个链接，可使用 # 开头的注释行）
set "AUTO_OPEN_URLS_FILE=%~dp0auto_urls.txt"

REM Cookie 导出保存目录
set "COOKIE_SAVE_DIR=D:\ai translate\cookie"

REM 远程调试端口起始值（每个沙箱窗口依次 +1）
set "REMOTE_DEBUG_BASE_PORT=9222"
REM ======================

set "SCRIPT_DIR=%~dp0"
set "POWERSHELL_EXPORT_SCRIPT=%SCRIPT_DIR%cookie_export.ps1"

cls
echo.
echo ======================================================
echo      批量创建 Chrome【真正隔离】的一次性环境
echo           (关闭窗口后自动清理本次痕迹)
echo ======================================================
echo.

REM 检查 Chrome 路径
if not exist "%chrome_path%" (
    echo [错误] 未找到 Chrome：%chrome_path%
    echo 请修改脚本顶部的 chrome_path 后再试。
    pause
    exit /b 1
)

REM 使用 PowerShell 生成时间戳，替代 wmic，避免编码/权限问题
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMddHHmmss')"`) do set "ldt=%%t"
set "SESSION_ID=%ldt%_%RANDOM%"
set "BASE_DIR=%TEMP%\ChromeSession_%SESSION_ID%"
set "SESSION_RECORD_FILE=%TEMP%\ChromeSession_%SESSION_ID%_dirs.log"

set "AUTO_URL_ARGS="
set "AUTO_URL_DISPLAY_LIST="
if defined AUTO_OPEN_URLS (
    set "INLINE_URLS=%AUTO_OPEN_URLS:;= %"
    for %%U in (!INLINE_URLS!) do (
        set "AUTO_URL_ARGS=!AUTO_URL_ARGS! \"%%~U\""
        if defined AUTO_URL_DISPLAY_LIST (
            set "AUTO_URL_DISPLAY_LIST=!AUTO_URL_DISPLAY_LIST!|%%~U"
        ) else (
            set "AUTO_URL_DISPLAY_LIST=%%~U"
        )
    )
)

if not defined AUTO_URL_ARGS (
    if defined AUTO_OPEN_URLS_FILE if exist "%AUTO_OPEN_URLS_FILE%" (
        for /f "usebackq tokens=* delims=" %%L in ("%AUTO_OPEN_URLS_FILE%") do (
            set "line=%%L"
            set "line=!line:"=!"
            if not "!line!"=="" (
                if /i not "!line:~0,1!"=="#" (
                    set "AUTO_URL_ARGS=!AUTO_URL_ARGS! \"!line!\""
                    if defined AUTO_URL_DISPLAY_LIST (
                        set "AUTO_URL_DISPLAY_LIST=!AUTO_URL_DISPLAY_LIST!|!line!"
                    ) else (
                        set "AUTO_URL_DISPLAY_LIST=!line!"
                    )
                )
            )
        )
    )
)

if defined AUTO_URL_ARGS (
    echo [提示] 将在每个沙箱窗口中自动打开以下链接:
    for %%Z in (!AUTO_URL_DISPLAY_LIST:|= !) do if not "%%~Z"=="" echo    %%~Z
    echo.
)

echo 本次会话 ID：%SESSION_ID%
echo 临时配置根目录：%BASE_DIR%
echo.

:ask
set /p num_windows="请输入需要打开的窗口数量 (输入数字后回车): "

REM 数字验证
set /a check_num=0
set /a check_num=%num_windows% 2>nul
if %check_num% LEQ 0 (
    echo.
    echo [提示] 请输入一个大于 0 的数字。
    echo.
    goto ask
)

echo.
echo 正在为您打开 %num_windows% 个完全隔离的浏览器窗口...
echo.

REM 创建根目录
mkdir "%BASE_DIR%" >nul 2>&1

set "SESSION_DIR_LIST="
set "SESSION_PORT_LIST="

REM 启动隔离窗口
for /l %%i in (1,1,%num_windows%) do (
    set "temp_profile_dir=%BASE_DIR%\P%%i"
    mkdir "!temp_profile_dir!" >nul 2>&1

    set /a port=%REMOTE_DEBUG_BASE_PORT%+%%i-1

    if defined SESSION_DIR_LIST (
        set "SESSION_DIR_LIST=!SESSION_DIR_LIST!|!temp_profile_dir!"
    ) else (
        set "SESSION_DIR_LIST=!temp_profile_dir!"
    )

    if defined SESSION_PORT_LIST (
        set "SESSION_PORT_LIST=!SESSION_PORT_LIST! !port!"
    ) else (
        set "SESSION_PORT_LIST=!port!"
    )

    set "CHROME_ARGS=--user-data-dir=\"!temp_profile_dir!\" --remote-debugging-port=!port! --remote-allow-origins=*"
    if "%USE_INCOGNITO%"=="1" (
        set "CHROME_ARGS=!CHROME_ARGS! --incognito"
    )

    start "Isolated Chrome %%i" "%chrome_path%" !CHROME_ARGS! !AUTO_URL_ARGS!
)

> "%SESSION_RECORD_FILE%" (
    echo 会话 ID: %SESSION_ID%
    echo 临时根目录: %BASE_DIR%
    echo.
    echo 本次创建的沙箱目录:
    for %%D in (!SESSION_DIR_LIST:|= !) do echo    %%D
    echo.
    echo 对应的远程调试端口:
    for %%P in (!SESSION_PORT_LIST!) do echo    %%P
)

echo.
echo [提示] 目录清单已记录在：%SESSION_RECORD_FILE%
echo        可随时打开查看。

echo [提示] 已启动。关闭这些窗口后，脚本会自动检测并清理本次会话的临时目录。
echo        如需保留，请在倒计时提示时按 N。
echo.
echo [操作] 在等待期间输入数字 1 可导出指定站点的 Cookie，直接回车则继续等待。

goto monitor_loop

:monitor_loop
call :GetProcCount
if %PROC_COUNT% LEQ 0 goto after_close

echo.
echo [状态] 当前本次会话的 Chrome 仍在运行（%PROC_COUNT% 个进程）。
set "USER_OPTION="
set /p USER_OPTION="输入 1 导出 Cookie，直接回车继续等待: "
if "%USER_OPTION%"=="1" goto ask_cookie_url

echo [提示] 继续等待浏览器关闭...
timeout /t 3 /nobreak >nul
goto monitor_loop

:ask_cookie_url
echo.
set "TARGET_URL="
set /p TARGET_URL="请输入完整网址（例如 https://example.com），留空取消: "
if not defined TARGET_URL (
    echo [提示] 已取消导出操作。
    goto monitor_loop
)
for /f "delims=" %%A in ("!TARGET_URL!") do set "REQUEST_URL=%%A"
call :ExportCookies
goto monitor_loop

:after_close
echo.
echo 检测到本次会话的所有 Chrome 窗口已关闭。
echo 即将清理以下目录：
for %%D in (!SESSION_DIR_LIST:|= !) do echo    %%D
echo    %BASE_DIR%
echo.
echo 目录清单亦可查看：%SESSION_RECORD_FILE%
echo.

echo 是否删除本次临时配置目录？默认 [Y] 8 秒后自动清理...
choice /C YN /N /T 8 /D Y /M "Y=清理  N=保留"
if errorlevel 2 goto retain_data

echo.
echo 正在清理...
for %%D in (!SESSION_DIR_LIST:|= !) do if exist "%%D" rd /s /q "%%D" 2>nul
rd /s /q "%BASE_DIR%" 2>nul

if exist "%BASE_DIR%" (
    echo [警告] 清理未完全成功（可能仍有文件被占用）。请稍后重试或手动删除：
    echo   %BASE_DIR%
) else (
    echo 清理完成，本次会话痕迹已删除。
    if exist "%SESSION_RECORD_FILE%" del /f /q "%SESSION_RECORD_FILE%" >nul 2>&1
)

goto the_end

:retain_data
echo.
echo 已选择保留临时目录：%BASE_DIR%
echo 目录明细保存在：%SESSION_RECORD_FILE%
goto the_end

:the_end
echo.
echo 操作完成，按任意键退出。
pause >nul
endlocal
exit /b 0

:GetProcCount
set "PROC_COUNT=0"
setlocal EnableDelayedExpansion
for /f "usebackq delims=" %%c in (`
    powershell -NoProfile -Command ^
      "$p=[regex]::Escape('!BASE_DIR!');(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -match $p }).Count"`
) do (
    endlocal
    set "PROC_COUNT=%%c"
    goto GetProcCountDone
)
endlocal
:GetProcCountDone
if not defined PROC_COUNT set "PROC_COUNT=0"
exit /b 0

:ExportCookies
setlocal EnableDelayedExpansion
if not defined REQUEST_URL (
    echo [提示] 未检测到待导出的网址。
    endlocal
    exit /b 0
)
set "REQ_URL=!REQUEST_URL!"
if "!REQ_URL!"=="" (
    echo [提示] 未输入网址。
    endlocal
    exit /b 0
)
if not defined SESSION_PORT_LIST (
    echo [提示] 当前没有已登记的调试端口，无法导出 Cookie。
    endlocal
    exit /b 0
)
if not exist "%POWERSHELL_EXPORT_SCRIPT%" (
    echo [错误] 缺少 cookie 导出脚本：%POWERSHELL_EXPORT_SCRIPT%
    endlocal
    exit /b 1
)

for /f "delims=" %%X in ("!REQ_URL!") do set "COOKIE_EXPORT_URL=%%X"
for /f "delims=" %%X in ("!SESSION_PORT_LIST!") do set "COOKIE_EXPORT_PORTS=%%X"
for /f "delims=" %%X in ("!COOKIE_SAVE_DIR!") do set "COOKIE_EXPORT_DIR=%%X"

set "PS_OUTPUT="
for /f "usebackq tokens=* delims=" %%O in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%POWERSHELL_EXPORT_SCRIPT%"`) do (
    set "PS_OUTPUT=%%O"
)

set "COOKIE_EXPORT_URL="
set "COOKIE_EXPORT_PORTS="
set "COOKIE_EXPORT_DIR="

if not defined PS_OUTPUT (
    echo [提示] 未获取到 PowerShell 输出，请确认目标站点已在沙箱中访问后重试。
) else (
    if /i "!PS_OUTPUT:~0,6!"=="SAVED:" (
        set "SAVE_PATH=!PS_OUTPUT:~6!"
        echo [成功] Cookie 已保存至：!SAVE_PATH!
    ) else if /i "!PS_OUTPUT!"=="NO_COOKIES" (
        echo [提示] 未获取到可用的 Cookie，请确保目标站点已在沙箱中登录/访问。
    ) else if /i "!PS_OUTPUT!"=="INVALID_URL" (
        echo [提示] 网址格式不正确，请重新输入。
    ) else if /i "!PS_OUTPUT!"=="NO_PORTS" (
        echo [提示] 当前没有可用的调试端口，Cookie 导出失败。
    ) else if /i "!PS_OUTPUT!"=="NO_DIR" (
        echo [提示] 未配置 Cookie 存储目录，请检查脚本顶部的 COOKIE_SAVE_DIR 设置。
    ) else if /i "!PS_OUTPUT!"=="EMPTY_URL" (
        echo [提示] 未提供网址，请重新输入。
    ) else (
        echo [提示] PowerShell 返回：!PS_OUTPUT!
    )
)

endlocal
exit /b 0
