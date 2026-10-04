param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PythonArguments)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the project virtual environment before running the pilot.'
}
$previousKey = $env:C1_PILOT_API_KEY
$pointer = [IntPtr]::Zero
try {
    if (-not $env:C1_PILOT_API_KEY) {
        $credentialPath = Join-Path $env:LOCALAPPDATA 'C1Pilot\qwen-api-key.dpapi'
        $secure = (Get-Content -LiteralPath $credentialPath -Raw).Trim() | ConvertTo-SecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $env:C1_PILOT_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    $env:HF_HOME = Join-Path $project '.cache\huggingface'
    Push-Location $project
    try {
        & $python @PythonArguments
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    $env:C1_PILOT_API_KEY = $previousKey
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}
exit $code
