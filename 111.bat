@echo off
REM 强制控制台使用 UTF-8，避免中文乱码
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM ====== 配置区域 ======
REM Chrome 路径（与实际不符请改）
set "chrome_path=C:\Program Files\Google\Chrome\Application\chrome.exe"

REM 是否使用无痕模式（1=启用，0=禁用）
set "USE_INCOGNITO=1"

REM Cookie 导出文件的根目录
set "COOKIE_OUTPUT_ROOT=D:\ai translate\cookie"

REM Chrome 远程调试端口起始值（每个窗口依次 +1）
set "REMOTE_DEBUG_PORT_START=9222"
REM ======================

cls
echo.
echo ======================================================
echo      批量创建 Chrome【真正隔离】的一次性环境
echo           (关闭窗口后自动清理本次痕迹)
echo ======================================================
echo.

where powershell >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 PowerShell，请在支持 PowerShell 的 Windows 环境中运行。
    pause
    exit /b 1
)

REM 检查 Chrome 路径
if not exist "%chrome_path%" (
    echo [错误] 未找到 Chrome：%chrome_path%
    echo 请修改脚本顶部的 chrome_path 后再试。
    pause
    exit /b 1
)

REM 生成会话标识
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMddHHmmss')"`) do set "ldt=%%t"
set "SESSION_ID=%ldt%_%RANDOM%"
set "BASE_DIR=%TEMP%\ChromeSession_%SESSION_ID%"
set "DIR_LOG=%BASE_DIR%\_created_dirs.txt"
set "PORT_LOG=%BASE_DIR%\_debug_ports.txt"
set "AUTO_URL_LIST_FILE=%BASE_DIR%\_auto_urls.txt"
set "COOKIE_SCRIPT=%BASE_DIR%\_export_cookie.ps1"
set "LAUNCH_SCRIPT=%BASE_DIR%\_launch_chrome.ps1"

echo 本次会话 ID：%SESSION_ID%
echo 临时配置根目录：%BASE_DIR%
echo.

REM 创建根目录及辅助文件
mkdir "%BASE_DIR%" >nul 2>&1
if errorlevel 1 (
    echo [错误] 无法创建临时目录：%BASE_DIR%
    pause
    exit /b 1
)

>"%DIR_LOG%" echo %BASE_DIR%
>"%PORT_LOG%" type nul >nul 2>&1
if exist "%AUTO_URL_LIST_FILE%" del "%AUTO_URL_LIST_FILE%" >nul 2>&1

call :create_launch_script
if errorlevel 1 (
    echo [错误] 初始化启动脚本失败。
    pause
    exit /b 1
)

call :create_cookie_script
if errorlevel 1 (
    echo [错误] 初始化 Cookie 导出脚本失败。
    pause
    exit /b 1
)

echo.
:ask_num
set "num_windows="
set /p "num_windows=请输入需要打开的窗口数量 (输入数字后回车): "
if not defined num_windows goto ask_num
set /a check_num=0
set /a check_num=%num_windows% 2>nul
if %check_num% LEQ 0 (
    echo.
    echo [提示] 请输入一个大于 0 的数字。
    echo.
    goto ask_num
)

REM 收集要自动打开的链接
set "AUTO_URL_COUNT=0"
echo.
echo 如需在每个窗口启动后自动打开网页，请逐一输入链接。
echo 输入完成后直接回车即可结束（本项可留空跳过）。
:collect_urls
set /a next_index=AUTO_URL_COUNT+1
set "CURRENT_URL="
set /p "CURRENT_URL=第 !next_index! 个链接: "
if defined CURRENT_URL (
    set /a AUTO_URL_COUNT+=1
    >>"%AUTO_URL_LIST_FILE%" echo(!CURRENT_URL!
    goto collect_urls
)
if !AUTO_URL_COUNT! GTR 0 (
    echo [信息] 已配置 !AUTO_URL_COUNT! 个链接，将在每个窗口自动打开。
) else (
    if exist "%AUTO_URL_LIST_FILE%" del "%AUTO_URL_LIST_FILE%" >nul 2>&1
    echo [信息] 本次未配置自动打开链接。
)

echo.
echo 正在为您打开 %num_windows% 个完全隔离的浏览器窗口...
echo.

REM 启动隔离窗口
for /l %%i in (1,1,%num_windows%) do (
    set "temp_profile_dir=%BASE_DIR%\P%%i"
    mkdir "!temp_profile_dir!" >nul 2>&1
    >>"%DIR_LOG%" echo !temp_profile_dir!

    set /a current_port=REMOTE_DEBUG_PORT_START + %%i - 1
    >>"%PORT_LOG%" echo !current_port!

    if "%USE_INCOGNITO%"=="1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCH_SCRIPT%" -ChromePath "%chrome_path%" -ProfileDir "!temp_profile_dir!" -DebugPort !current_port! -UrlsFile "%AUTO_URL_LIST_FILE%" -Incognito >nul 2>&1
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCH_SCRIPT%" -ChromePath "%chrome_path%" -ProfileDir "!temp_profile_dir!" -DebugPort !current_port! -UrlsFile "%AUTO_URL_LIST_FILE%" >nul 2>&1
    )
)

echo.
echo [提示] 已启动。关闭这些窗口后，脚本会自动检测并清理本次会话的临时目录。
echo        如需保留，请在倒计时提示时按 N。
echo [提示] 等待期间可按 C 键导出指定网站的 Cookie，文件将保存至：%COOKIE_OUTPUT_ROOT%
echo.

REM ========= 仅监控本次会话相关的 chrome 进程 =========
:waitloop
set "PROC_COUNT=0"
for /f "usebackq delims=" %%c in (`
    powershell -NoProfile -Command ^
      "$p=[regex]::Escape('%BASE_DIR%');" ^
      ";(Get-CimInstance Win32_Process ^| Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -match $p }).Count"`
) do set "PROC_COUNT=%%c"

if not defined PROC_COUNT set "PROC_COUNT=0"

if %PROC_COUNT% GTR 0 (
    choice /C CY /N /T 2 /D Y /M "按 C 导出 Cookie，或等待自动检测..."
    if errorlevel 2 goto waitloop
    if errorlevel 1 (
        call :handle_cookie_export
    )
    goto waitloop
)

echo.
echo 检测到本次会话的所有 Chrome 窗口已关闭。
echo 将尝试清理以下目录：
echo -----------------------------------------
if exist "%DIR_LOG%" (
    for /f "usebackq delims=" %%d in ("%DIR_LOG%") do echo    %%d
) else (
    echo    %BASE_DIR%
)
echo -----------------------------------------
echo.

echo 是否删除本次临时配置目录？默认 [Y] 8 秒后自动清理...
choice /C YN /N /T 8 /D Y /M "Y=清理  N=保留"
if errorlevel 2 (
    echo.
    echo 已选择保留临时目录：%BASE_DIR%
    echo 你可以稍后手动删除以回收空间。
    goto the_end
)

echo.
echo 正在清理...
if exist "%DIR_LOG%" (
    for /f "usebackq delims=" %%d in ("%DIR_LOG%") do (
        if exist "%%~d" (
            rd /s /q "%%~d" 2>nul
        )
    )
) else (
    rd /s /q "%BASE_DIR%" 2>nul
)

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

REM ========================================================
REM 函数定义区域
REM ========================================================
:handle_cookie_export
echo.
set "COOKIE_PROMPT="
set /p "COOKIE_PROMPT=请输入要导出 Cookie 的网址或域名（直接回车取消）: "
if not defined COOKIE_PROMPT (
    echo [提示] 已取消导出。
    goto :eof
)
set "COOKIE_REQUEST=%COOKIE_PROMPT%"
call :run_cookie_export
if errorlevel 1 (
    echo [错误] Cookie 导出过程中出现问题（详见上方输出）。
) else (
    echo [提示] Cookie 导出任务已完成。
)
set "COOKIE_REQUEST="
goto :eof

:run_cookie_export
setlocal
if not defined COOKIE_REQUEST (
    endlocal
    exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%COOKIE_SCRIPT%" -PortListPath "%PORT_LOG%" -OutputRoot "%COOKIE_OUTPUT_ROOT%"
set "ps_error=%ERRORLEVEL%"
endlocal & exit /b %ps_error%

:create_launch_script
setlocal DisableDelayedExpansion
>"%LAUNCH_SCRIPT%" (
    echo param^(^
    echo     ^[Parameter^(Mandatory=$true^)] [string]$ChromePath,
    echo     ^[Parameter^(Mandatory=$true^)] [string]$ProfileDir,
    echo     ^[Parameter^(Mandatory=$true^)] [int]$DebugPort,
    echo     [string]$UrlsFile,
    echo     [switch]$Incognito
    echo ^)
    echo try {
    echo     if (-not (Test-Path -LiteralPath $ChromePath)) {
    echo         Write-Output "^[launch^] Chrome 路径无效：$ChromePath"
    echo         exit 1
    echo     }
    echo
    echo     $arguments = @("--user-data-dir=`"$ProfileDir`"","--remote-debugging-port=$DebugPort","--no-default-browser-check","--no-first-run")
    echo     if ($Incognito.IsPresent) {
    echo         $arguments += "--incognito"
    echo     }
    echo
    echo     if ($UrlsFile -and (Test-Path -LiteralPath $UrlsFile)) {
    echo         $urls = Get-Content -LiteralPath $UrlsFile ^| Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    echo         foreach ($url in $urls) {
    echo             $trimmed = $url.Trim()
    echo             if ($trimmed) {
    echo                 $arguments += $trimmed
    echo             }
    echo         }
    echo     }
    echo
    echo     Start-Process -FilePath $ChromePath -ArgumentList $arguments ^| Out-Null
    echo } catch {
    echo     Write-Output "^[launch^] 无法启动 Chrome：$($_.Exception.Message)"
    echo     exit 1
    echo }
)
if errorlevel 1 (
    endlocal
    exit /b 1
)
endlocal
exit /b 0

:create_cookie_script
setlocal DisableDelayedExpansion
>"%COOKIE_SCRIPT%" (
    echo param^(^
    echo     ^[Parameter^(Mandatory=$true^)] [string]$PortListPath,
    echo     ^[Parameter^(Mandatory=$true^)] [string]$OutputRoot
    echo ^)
    echo
    echo $targetInput = [Environment]::GetEnvironmentVariable('COOKIE_REQUEST','Process')
    echo if ([string]::IsNullOrWhiteSpace($targetInput)) {
    echo     Write-Output "^[信息^] 未输入网址，已取消导出。"
    echo     exit 0
    echo }
    echo
    echo $target = $targetInput.Trim()
    echo $uri = $null
    echo $urlsToQuery = New-Object System.Collections.Generic.List[string]
    echo if ([Uri]::TryCreate($target, [UriKind]::Absolute, [ref]$uri)) {
    echo     # 已获取绝对地址
    echo } elseif ([Uri]::TryCreate("https://$target", [UriKind]::Absolute, [ref]$uri)) {
    echo     # 尝试以 https 补全
    echo } elseif ([Uri]::TryCreate("http://$target", [UriKind]::Absolute, [ref]$uri)) {
    echo     # 尝试以 http 补全
    echo } else {
    echo     Write-Output "^[错误^] 无法解析网址：$target"
    echo     exit 1
    echo }
    echo
    echo $domain = $uri.Host
    echo if (-not $domain) {
    echo     Write-Output "^[错误^] 无法确定域名，请确认输入是否正确。"
    echo     exit 1
    echo }
    echo
    echo $urlsToQuery.Add($uri.AbsoluteUri) ^| Out-Null
    echo if ($uri.Scheme -ne 'https') {
    echo     $urlsToQuery.Add("https://$domain/") ^| Out-Null
    echo }
    echo if ($uri.Scheme -ne 'http') {
    echo     $urlsToQuery.Add("http://$domain/") ^| Out-Null
    echo }
    echo $urlsToQuery = $urlsToQuery ^| Select-Object -Unique
    echo
    echo if (-not (Test-Path -LiteralPath $PortListPath)) {
    echo     Write-Output "^[错误^] 未找到调试端口列表，无法导出 Cookie。"
    echo     exit 1
    echo }
    echo $ports = Get-Content -LiteralPath $PortListPath 2^>^&1 ^| ForEach-Object { $_.Trim() } ^| Where-Object { $_ -match '^[0-9]+$' }
    echo if (-not $ports) {
    echo     Write-Output "^[错误^] 调试端口列表为空，无法导出 Cookie。"
    echo     exit 1
    echo }
    echo
    echo function Receive-DevToolsMessage {
    echo     param(
    echo         [System.Net.WebSockets.ClientWebSocket]$Client,
    echo         [int]$ExpectedId
    echo     )
    echo
    echo     $buffer = New-Object byte[] 4096
    echo     while ($true) {
    echo         $builder = New-Object System.Text.StringBuilder
    echo         do {
    echo             $segment = [System.ArraySegment[byte]]::new($buffer, 0, $buffer.Length)
    echo             $result = $Client.ReceiveAsync($segment, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    echo             if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
    echo                 return $null
    echo             }
    echo             if ($result.Count -gt 0) {
    echo                 $builder.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)) ^| Out-Null
    echo             }
    echo         } while (-not $result.EndOfMessage)
    echo
    echo         $text = $builder.ToString()
    echo         if (-not [string]::IsNullOrEmpty($text)) {
    echo             try {
    echo                 $obj = $text ^| ConvertFrom-Json -Depth 6
    echo             } catch {
    echo                 continue
    echo             }
    echo             if ($obj -and $obj.id -eq $ExpectedId) {
    echo                 return $obj
    echo             }
    echo         }
    echo     }
    echo }
    echo
    echo function Send-DevToolsCommand {
    echo     param(
    echo         [System.Net.WebSockets.ClientWebSocket]$Client,
    echo         [hashtable]$Command
    echo     )
    echo
    echo     $json = $Command ^| ConvertTo-Json -Compress -Depth 6
    echo     $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    echo     $segment = [System.ArraySegment[byte]]::new($bytes, 0, $bytes.Length)
    echo     $Client.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    echo }

    echo
    echo function Get-CookiesFromTarget {
    echo     param(
    echo         [string]$DebuggerUrl,
    echo         [string[]]$Urls
    echo     )
    echo
    echo     $client = [System.Net.WebSockets.ClientWebSocket]::new()
    echo     try {
    echo         $client.Options.KeepAliveInterval = [TimeSpan]::FromSeconds(5)
    echo         $client.ConnectAsync([Uri]$DebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    echo
    echo         $commandId = 1
    echo         Send-DevToolsCommand -Client $client -Command @{ id = $commandId; method = "Network.enable" }
    echo         Receive-DevToolsMessage -Client $client -ExpectedId $commandId ^| Out-Null
    echo
    echo         $commandId++
    echo         Send-DevToolsCommand -Client $client -Command @{ id = $commandId; method = "Network.getCookies"; params = @{ urls = $Urls } }
    echo         $response = Receive-DevToolsMessage -Client $client -ExpectedId $commandId
    echo         if ($null -ne $response -and $response.result -and $response.result.cookies) {
    echo             return $response.result.cookies
    echo         }
    echo         return @()
    echo     } catch {
    echo         return @()
    echo     } finally {
    echo         if ($client.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
    echo             $client.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    echo         }
    echo         $client.Dispose()
    echo     }
    echo }
    echo
    echo $cookiesMap = @{}
    echo foreach ($port in $ports) {
    echo     try {
    echo         $targets = Invoke-RestMethod -Uri "http://127.0.0.1:$port/json" -TimeoutSec 2
    echo     } catch {
    echo         continue
    echo     }
    echo
    echo     foreach ($targetInfo in $targets) {
    echo         if (-not $targetInfo.webSocketDebuggerUrl) { continue }
    echo         $cookies = Get-CookiesFromTarget -DebuggerUrl $targetInfo.webSocketDebuggerUrl -Urls $urlsToQuery
    echo         foreach ($cookie in $cookies) {
    echo             $key = "{0}|{1}|{2}" -f $cookie.domain, $cookie.name, $cookie.path
    echo             $cookiesMap[$key] = $cookie
    echo         }
    echo     }
    echo }
    echo
    echo $allCookies = $cookiesMap.Values
    echo
    echo try {
    echo     if (-not (Test-Path -LiteralPath $OutputRoot)) {
    echo         New-Item -ItemType Directory -Path $OutputRoot -Force ^| Out-Null
    echo     }
    echo } catch {
    echo     Write-Output "^[错误^] 无法创建或访问输出目录：$OutputRoot"
    echo     exit 1
    echo }
    echo
    echo $invalid = [System.IO.Path]::GetInvalidFileNameChars()
    echo $safeDomainChars = $domain.ToCharArray() ^| ForEach-Object { if ($invalid -contains $_) { '_' } else { $_ } }
    echo $safeDomain = -join $safeDomainChars
    echo if (-not $safeDomain) { $safeDomain = 'unknown-domain' }
    echo $randomSuffix = Get-Random -Minimum 10000 -Maximum 99999
    echo $fileName = "{0}{1}.txt" -f $safeDomain, $randomSuffix
    echo $filePath = [System.IO.Path]::Combine($OutputRoot, $fileName)
    echo
    echo $lines = New-Object System.Collections.Generic.List[string]
    echo $lines.Add("导出时间(本地): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')") ^| Out-Null
    echo $lines.Add("目标输入: $targetInput") ^| Out-Null
    echo $lines.Add("解析域名: $domain") ^| Out-Null
    echo $lines.Add("查询链接: " + ($urlsToQuery -join ', ')) ^| Out-Null
    echo $lines.Add("----------------------------------------") ^| Out-Null
    echo
    echo if ($allCookies -and $allCookies.Count -gt 0) {
    echo     $sorted = $allCookies ^| Sort-Object -Property domain, path, name
    echo     foreach ($cookie in $sorted) {
    echo         $lines.Add("Name: $($cookie.name)") ^| Out-Null
    echo         $lines.Add("Value: $($cookie.value)") ^| Out-Null
    echo         $lines.Add("Domain: $($cookie.domain)") ^| Out-Null
    echo         $lines.Add("Path: $($cookie.path)") ^| Out-Null
    echo         if ($cookie.expires -and $cookie.expires -gt 0) {
    echo             $expires = [DateTimeOffset]::FromUnixTimeSeconds([long]$cookie.expires).UtcDateTime.ToString('yyyy-MM-dd HH:mm:ss') + ' UTC'
    echo         } else {
    echo             $expires = 'Session'
    echo         }
    echo         $lines.Add("Expires: $expires") ^| Out-Null
    echo         $lines.Add("HttpOnly: $($cookie.httpOnly)") ^| Out-Null
    echo         $lines.Add("Secure: $($cookie.secure)") ^| Out-Null
    echo         if ($cookie.sameSite) {
    echo             $lines.Add("SameSite: $($cookie.sameSite)") ^| Out-Null
    echo         }
    echo         $lines.Add("----------------------------------------") ^| Out-Null
    echo     }
    echo } else {
    echo     $lines.Add("未获取到任何匹配的 Cookie。") ^| Out-Null
    echo }
    echo
    echo try {
    echo     Set-Content -LiteralPath $filePath -Value $lines -Encoding UTF8
    echo } catch {
    echo     Write-Output "^[错误^] 无法写入文件：$filePath"
    echo     exit 1
    echo }
    echo
    echo Write-Output "^[成功^] Cookie 已保存至：$filePath"
    echo exit 0
)
if errorlevel 1 (
    endlocal
    exit /b 1
)
endlocal
exit /b 0

