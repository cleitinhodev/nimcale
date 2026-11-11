# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke tests of the frozen Windows build (dist\Nimcale\Nimcale.exe). Used by GitHub Actions.
# Every run uses the same code path as a user double-clicking the exe, and fails on a non-zero exit
# code, a Python traceback or an error line in nimcale.log.
param([string]$Exe = "dist\Nimcale\Nimcale.exe", [string]$Work = "$env:RUNNER_TEMP\nimcale_smoke")
$ErrorActionPreference = "Stop"
$env:NIMCALE_NO_DIALOGS = "1"          # error dialogs would block the runner forever
New-Item -ItemType Directory -Force $Work | Out-Null
$Exe = (Resolve-Path $Exe).Path
$failed = @()

function Invoke-Nimcale([string]$Name, [string[]]$ArgList, [string]$Cfg, [int]$TimeoutSec = 300) {
    $env:NIMCALE_CONFIG_DIR = $Cfg
    New-Item -ItemType Directory -Force $Cfg | Out-Null
    Write-Host "=== $Name : Nimcale.exe $($ArgList -join ' ')"
    $p = Start-Process -FilePath $Exe -ArgumentList $ArgList -PassThru
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { $p.Kill(); throw "$Name : timeout after $TimeoutSec s" }
    $log = Join-Path $Cfg "nimcale.log"
    $text = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
    Write-Host $text
    return @{ Code = $p.ExitCode; Log = $text }
}

function Assert-CleanRun($r, [string]$Name, [string[]]$MustContain) {
    $errs = @()
    if ($r.Code -ne 0) { $errs += "exit code $($r.Code)" }
    foreach ($bad in @("Traceback", "[error]", "ERROR:", "AttributeError", "Failed to load GLFW", "PROBE ERROR")) {
        if ($r.Log.Contains($bad)) { $errs += "log contains '$bad'" }
    }
    foreach ($m in $MustContain) { if (-not $r.Log.Contains($m)) { $errs += "log lacks '$m'" } }
    if ($errs.Count) { $script:failed += "$Name : $($errs -join '; ')"; Write-Host "FAILED $Name : $($errs -join '; ')" }
    else { Write-Host "OK $Name" }
}

# 1) the GL probe itself works in the frozen exe (GLFW DLL found, context created with Mesa)
$probe = Join-Path $Work "probe_sw.txt"
$env:NIMCALE_CONFIG_DIR = Join-Path $Work "cfg_probe"
$p = Start-Process -FilePath $Exe -ArgumentList @("--probe-gl", "--software", "--probe-out", $probe) -PassThru -Wait
$out = if (Test-Path $probe) { Get-Content $probe -Raw } else { "" }
Write-Host "software probe (exit $($p.ExitCode)): $out"
if ($p.ExitCode -ne 0 -or -not $out.Contains("PROBE OK")) { $failed += "software probe: $out" }

# 2) the GPU probe must give a real answer (OK or FAIL), never an infrastructure error
$probe = Join-Path $Work "probe_gpu.txt"
$p = Start-Process -FilePath $Exe -ArgumentList @("--probe-gl", "--probe-out", $probe) -PassThru -Wait
$out = if (Test-Path $probe) { Get-Content $probe -Raw } else { "" }
Write-Host "GPU probe (exit $($p.ExitCode)): $out"
if ($out.Contains("PROBE ERROR") -or -not ($out.Contains("PROBE OK") -or $out.Contains("PROBE FAIL"))) {
    $failed += "GPU probe: $out"
}

# 3) first start exactly like a double click (automatic renderer choice, saved layout path), then a second start
$cfg = Join-Path $Work "cfg_user"
$r = Invoke-Nimcale "first start (auto renderer)" @("--quit-after", "90") $cfg
Assert-CleanRun $r "first start" @("GPU probe:", "renderer:", "OpenGL:", "title bar: mode=system", "quit-after:")
($r.Log -split "`n") | Where-Object { $_ -like "title bar:*" } | ForEach-Object { Write-Host "TITLE BAR (default): $_" }
# second start: saved settings/layout, and the title bar set to the purple "theme" mode
$cfgFile = Join-Path $cfg "config.json"
$j = Get-Content $cfgFile -Raw | ConvertFrom-Json
$j | Add-Member -NotePropertyName titlebar -NotePropertyValue "theme" -Force
$j | ConvertTo-Json -Depth 5 | Set-Content $cfgFile -Encoding utf8
$r = Invoke-Nimcale "second start (saved settings + layout, theme title bar)" @("--quit-after", "90") $cfg
Assert-CleanRun $r "second start" @("renderer:", "OpenGL:", "title bar: mode=theme", "quit-after:")
($r.Log -split "`n") | Where-Object { $_ -like "title bar:*" } | ForEach-Object { Write-Host "TITLE BAR (theme): $_" }
if (-not $r.Log.Contains("applied=dwm")) { Write-Host "::warning::DwmSetWindowAttribute was not applied on this runner" }

# 4) forced software renderer + screenshot
$shot = Join-Path $env:GITHUB_WORKSPACE "ci_shot.png"
$r = Invoke-Nimcale "software renderer + screenshot" @("--software", "--frames", "40", "--size", "1440x900", "--shot", $shot) (Join-Path $Work "cfg_sw")
Assert-CleanRun $r "software screenshot" @("renderer: software", "OpenGL:", "shot:")
if (-not (Test-Path $shot)) { $failed += "no screenshot" }

# 5) non-GUI self test (mesh + STL)
$r = Invoke-Nimcale "selftest" @("--selftest") (Join-Path $Work "cfg_self")
Assert-CleanRun $r "selftest" @("'watertight': True", "selftest surface: obj:", "dae:", "watertight=True")

if ($failed.Count) { Write-Host "`nSMOKE TEST FAILURES:"; $failed | ForEach-Object { Write-Host " - $_" }; exit 1 }
Write-Host "`nAll smoke tests passed."
