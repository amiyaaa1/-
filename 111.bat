@echo off
REM 强制控制台使用 UTF-8，避免中文乱码
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ====== 配置区域 ======
REM Chrome 路径（与实际不符请改）
set "chrome_path=C:\Program Files\Google\Chrome\Application\chrome.exe"

REM 是否使用无痕模式（1=启用，0=禁用）
set "USE_INCOGNITO=1"
REM ======================

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

REM 启动隔离窗口
for /l %%i in (1,1,%num_windows%) do (
    set "temp_profile_dir=%BASE_DIR%\P%%i"
    mkdir "!temp_profile_dir!" >nul 2>&1

    if "%USE_INCOGNITO%"=="1" (
        start "Isolated Chrome %%i" "%chrome_path%" --user-data-dir="!temp_profile_dir!" --incognito
    ) else (
        start "Isolated Chrome %%i" "%chrome_path%" --user-data-dir="!temp_profile_dir!"
    )
)

echo.
echo [提示] 已启动。关闭这些窗口后，脚本会自动检测并清理本次会话的临时目录。
echo        如需保留，请在倒计时提示时按 N。
echo.

REM ========= 仅监控本次会话相关的 chrome 进程 =========
:waitloop
for /f "usebackq delims=" %%c in (`
    powershell -NoProfile -Command ^
      "$p=[regex]::Escape('%BASE_DIR%');" ^
      ";(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -match $p }).Count"
`) do set "PROC_COUNT=%%c"

if not defined PROC_COUNT set "PROC_COUNT=0"

if %PROC_COUNT% GTR 0 (
    timeout /t 2 /nobreak >nul
    goto :waitloop
)

echo.
echo 检测到本次会话的所有 Chrome 窗口已关闭。
echo 将清理：%BASE_DIR%
echo.

REM ========= 自动清理（8 秒倒计时，可取消） =========
echo 是否删除本次临时配置目录？默认 [Y] 8 秒后自动清理...
choice /C YN /N /T 8 /D Y /M "Y=清理  N=保留"
if errorlevel 2 (
    echo.
    echo 已选择保留临时目录：%BASE_DIR%
    echo 你可以稍后手动删除以回收空间。
    goto :the_end
)

echo.
echo 正在清理...
rd /s /q "%BASE_DIR%" 2>nul

if exist "%BASE_DIR%" (
    echo [警告] 清理未完全成功（可能仍有文件被占用）。请稍后重试或手动删除：
    echo   %BASE_DIR%
) else (
    echo 清理完成，本次会话痕迹已删除。
)

:the_end
echo.
echo 操作完成，按任意键退出。
pause >nul
endlocal
exit /b 0
