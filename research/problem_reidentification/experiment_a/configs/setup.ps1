$ErrorActionPreference = 'Stop'
$experimentRoot = Split-Path -Parent $PSScriptRoot
$experimentRoot = (Resolve-Path -LiteralPath $experimentRoot).Path
$sourceRoot = Join-Path $experimentRoot 'local/upstream'
New-Item -ItemType Directory -Force $sourceRoot | Out-Null
$projects = @(
    @{ Name='MedCPT'; Url='https://github.com/ncbi/MedCPT.git'; Commit='11e129be74102c98d16a11c310b0b5ce74c1db5e' },
    @{ Name='TrialGPT'; Url='https://github.com/ncbi-nlp/TrialGPT.git'; Commit='1b3242cd50c153a9c324661d4a0bd94fc68a4226' },
    @{ Name='consumer-health-research'; Url='https://github.com/Google-Health/consumer-health-research.git'; Commit='3e9d1e4877a54cf81ce8ef34085006952dd19601' }
)
foreach ($project in $projects) {
    $target = Join-Path $sourceRoot $project.Name
    if (-not (Test-Path -LiteralPath $target)) {
        & git clone --filter=blob:none $project.Url $target
        if ($LASTEXITCODE -ne 0) { throw 'Official clone failed' }
        & git -C $target checkout --detach $project.Commit
        if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed' }
    }
    $actual = (& git -C $target rev-parse HEAD).Trim()
    $dirty = & git -C $target status --porcelain --untracked-files=no
    if ($actual -ne $project.Commit -or $dirty) { throw "Existing official checkout differs: $($project.Name)" }
}
foreach ($name in @('medcpt','trialgpt','pha')) {
    $version = if ($name -eq 'pha') { '3.12' } else { '3.11' }
    $environmentPath = Join-Path $experimentRoot "local/envs/$name"
    $interpreterPath = Join-Path $environmentPath 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $interpreterPath)) {
        & uv venv $environmentPath --python $version
        if ($LASTEXITCODE -ne 0) { throw 'Isolated environment creation failed' }
    }
    # Every installed dependency is explicitly locked. OneTwo optional Gemma/TF
    # dependencies are intentionally not resolved, following upstream setup's --no-deps path.
    & uv pip install --python $interpreterPath --no-deps -r (Join-Path $PSScriptRoot "$name.lock.txt")
    if ($LASTEXITCODE -ne 0) { throw "Locked install failed: $name" }
}
