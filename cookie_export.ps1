[CmdletBinding()]
param(
    [string]$Url,
    [string[]]$Ports,
    [string]$CookieDir
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $Url) {
    $Url = $env:COOKIE_EXPORT_URL
}

if (-not $Ports -or $Ports.Count -eq 0) {
    if ($env:COOKIE_EXPORT_PORTS) {
        $Ports = $env:COOKIE_EXPORT_PORTS -split '[,\s]+'
    }
}

if (-not $CookieDir) {
    $CookieDir = $env:COOKIE_EXPORT_DIR
}

if ([string]::IsNullOrWhiteSpace($Url)) {
    Write-Output 'EMPTY_URL'
    exit 1
}

try {
    $targetUri = [Uri]$Url
} catch {
    Write-Output 'INVALID_URL'
    exit 2
}

if (-not $Ports -or $Ports.Count -eq 0) {
    Write-Output 'NO_PORTS'
    exit 3
}

if (-not $CookieDir) {
    Write-Output 'NO_DIR'
    exit 4
}

if (-not [IO.Directory]::Exists($CookieDir)) {
    [IO.Directory]::CreateDirectory($CookieDir) | Out-Null
}

function Send-Message {
    param(
        [Parameter(Mandatory = $true)][System.Net.WebSockets.ClientWebSocket]$Socket,
        [Parameter(Mandatory = $true)][string]$Message
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Message)
    $segment = New-Object System.ArraySegment[byte] ($bytes, 0, $bytes.Length)
    $Socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).Wait()
}

function Receive-Message {
    param(
        [Parameter(Mandatory = $true)][System.Net.WebSockets.ClientWebSocket]$Socket
    )

    $buffer = New-Object byte[] 4096
    $builder = New-Object System.Text.StringBuilder

    do {
        $segment = New-Object System.ArraySegment[byte] ($buffer, 0, $buffer.Length)
        $result = $Socket.ReceiveAsync($segment, [Threading.CancellationToken]::None).Result
        if ($result.Count -gt 0) {
            $null = $builder.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
        }
    } while (-not $result.EndOfMessage)

    return $builder.ToString()
}

$cookies = @()

foreach ($portString in $Ports) {
    if ([string]::IsNullOrWhiteSpace($portString)) {
        continue
    }

    try {
        $port = [int]$portString
    } catch {
        continue
    }

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/json" -f $port)
        if (-not $response.Content) {
            continue
        }
        $targets = $response.Content | ConvertFrom-Json
    } catch {
        continue
    }

    foreach ($target in $targets) {
        if (-not $target.webSocketDebuggerUrl) {
            continue
        }

        $socket = New-Object System.Net.WebSockets.ClientWebSocket

        try {
            $socket.ConnectAsync([Uri]$target.webSocketDebuggerUrl, [Threading.CancellationToken]::None).Wait(3000) | Out-Null
            if ($socket.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
                continue
            }

            Send-Message -Socket $socket -Message '{"id":1,"method":"Network.enable"}'
            $null = Receive-Message -Socket $socket

            $payload = @{ id = 2; method = 'Network.getCookies'; params = @{ urls = @($Url) } } | ConvertTo-Json -Depth 5 -Compress
            Send-Message -Socket $socket -Message $payload
            $reply = Receive-Message -Socket $socket

            if (-not $reply) {
                continue
            }

            try {
                $data = $reply | ConvertFrom-Json
            } catch {
                continue
            }

            if ($data.id -eq 2 -and $data.result -and $data.result.cookies) {
                $cookies += $data.result.cookies
                break
            }
        } catch {
            continue
        } finally {
            if ($socket) {
                $socket.Dispose()
            }
        }
    }
}

if ($cookies.Count -eq 0) {
    Write-Output 'NO_COOKIES'
    exit 5
}

$unique = $cookies | Sort-Object domain, name, path -Unique
$rand = Get-Random -Minimum 1000 -Maximum 999999
$fileName = '{0}_{1}.txt' -f $targetUri.Host, $rand
$filePath = Join-Path -Path $CookieDir -ChildPath $fileName
$unique | ConvertTo-Json -Depth 5 | Out-File -FilePath $filePath -Encoding utf8
Write-Output ("SAVED:{0}" -f $filePath)
exit 0
