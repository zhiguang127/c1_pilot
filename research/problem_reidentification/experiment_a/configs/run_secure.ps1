param(
    [Parameter(Mandatory=$true)][ValidateSet('trialgpt','pha')][string]$Environment,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$PythonArguments
)
$ErrorActionPreference = 'Stop'
$experimentRoot = Split-Path -Parent $PSScriptRoot
$experimentPython = Join-Path $experimentRoot "local/envs/$Environment/Scripts/python.exe"
$previousKey = $env:C1_PILOT_API_KEY
$previousBase = $env:OPENAI_BASE_URL
$previousEncoding = $env:PYTHONUTF8
$pointer = [IntPtr]::Zero
try {
    if (-not $env:C1_PILOT_API_KEY) {
        $env:C1_PILOT_API_KEY = [Environment]::GetEnvironmentVariable('C1_PILOT_API_KEY', 'User')
    }
    if (-not $env:C1_PILOT_API_KEY) {
        $credentialPath = Join-Path $env:LOCALAPPDATA 'C1Pilot/qwen-api-key.dpapi'
        $secure = (Get-Content -LiteralPath $credentialPath -Raw).Trim() | ConvertTo-SecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $env:C1_PILOT_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    $env:OPENAI_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    $env:PYTHONUTF8 = '1'
    & $experimentPython @PythonArguments
    $exitCode = $LASTEXITCODE
} finally {
    $env:C1_PILOT_API_KEY = $previousKey
    $env:OPENAI_BASE_URL = $previousBase
    $env:PYTHONUTF8 = $previousEncoding
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
exit $exitCode
