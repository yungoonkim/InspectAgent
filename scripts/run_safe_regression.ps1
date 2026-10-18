[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$Browser = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Run = Join-Path $Root ("data/outputs/safe-regression/" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Path $Run | Out-Null
$Results = [System.Collections.Generic.List[object]]::new()
$InitialLocation = Get-Location
$OriginalBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = "1"

function Add-Result([string]$Name, [int]$Passed, [int]$Failed, [int]$Skipped, [string]$Reason = "") {
    $Results.Add([pscustomobject]@{name=$Name; pass=$Passed; fail=$Failed; skip=$Skipped; warnings=0; reason=$Reason})
    Write-Host ("{0}: PASS={1} FAIL={2} SKIP={3} {4}" -f $Name,$Passed,$Failed,$Skipped,$Reason)
}

function Invoke-Check([string]$Name, [scriptblock]$Action) {
    $log = Join-Path $Run ($Name + ".log")
    try {
        $local:ErrorActionPreference = "Continue"
        $global:LASTEXITCODE = $null
        & $Action 2>&1 | Tee-Object -FilePath $log | Out-Host
        $code = $LASTEXITCODE
        if ($null -eq $code -or $code -ne 0) { Add-Result $Name 0 1 0 "exit=$code" }
        else { Add-Result $Name 1 0 0 }
    } catch {
        $_ | Out-String | Add-Content -LiteralPath $log
        Add-Result $Name 0 1 0 $_.Exception.GetType().Name
    }
}

try {
    Set-Location $Root
    if (!$Python) {
        $candidates = @()
        if ($env:CONDA_PREFIX -and (Split-Path -Leaf $env:CONDA_PREFIX) -eq "vision-insight") {
            $candidates += Join-Path $env:CONDA_PREFIX "python.exe"
        }
        $candidates += Join-Path $env:USERPROFILE "miniconda3/envs/vision-insight/python.exe"
        $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (!$Python) { throw "Miniconda vision-insight Python not found; pass -Python explicitly" }
    & $Python -B scripts/safe_regression_backend.py snapshot --output $Run
    if ($LASTEXITCODE -ne 0) { throw "Operational fingerprint snapshot failed" }
    Invoke-Check "backend" { & $Python -B scripts/safe_regression_backend.py backend --output $Run }
    $xmlPath = Join-Path $Run "backend.xml"
    if (Test-Path -LiteralPath $xmlPath) {
        [xml]$xml = Get-Content -LiteralPath $xmlPath -Raw
        $suite = $xml.testsuites.testsuite
        $failed = [int]$suite.failures + [int]$suite.errors
        $skipped = [int]$suite.skipped
        $passed = [int]$suite.tests - $failed - $skipped
        $stage = $Results | Where-Object name -eq "backend"
        $safetyFailure = $stage.fail -gt 0 -and $failed -eq 0
        $stage.pass=$passed; $stage.fail=$failed + [int]$safetyFailure; $stage.skip=$skipped
        Write-Host "Backend cases: PASS=$passed FAIL=$($stage.fail) SKIP=$skipped"
    } else {
        $stage = $Results | Where-Object name -eq "backend"
        $stage.pass=0; $stage.fail=1; $stage.reason="Missing backend.xml"
    }
    if (!(Test-Path frontend/node_modules/.bin/tsc.cmd)) {
        Add-Result "frontend" 0 0 1 "Dependencies missing; no installation attempted"
        Add-Result "typescript" 0 0 1 "Dependencies missing"
        Add-Result "lint" 0 0 1 "Dependencies missing"
        Add-Result "build" 0 0 1 "Dependencies missing"
        Add-Result "browser-e2e" 0 0 1 "Dependencies missing"
        Add-Result "agent-browser-e2e" 0 0 1 "Dependencies missing"
        Add-Result "grab-browser-e2e" 0 0 1 "Dependencies missing"
        Add-Result "roi-browser-e2e" 0 0 1 "Dependencies missing"
        Add-Result "vision-browser-e2e" 0 0 1 "Dependencies missing"
    } else {
        Invoke-Check "frontend" { & node --test --test-reporter=tap frontend/scripts/test_image_transform.mjs frontend/test_f31_units.js frontend/scripts/test_step4_regression.mjs frontend/scripts/test_agent_analysis_state.mjs frontend/scripts/test_grab_inspection.mjs frontend/scripts/test_reinspection_state.mjs frontend/scripts/test_roi_vision_state.mjs }
        $tap = Get-Content -LiteralPath (Join-Path $Run "frontend.log") -Raw
        $stage = $Results | Where-Object name -eq "frontend"
        $matchPass = [regex]::Match($tap, '(?m)^# pass\s+(\d+)')
        $matchFail = [regex]::Match($tap, '(?m)^# fail\s+(\d+)')
        $matchSkip = [regex]::Match($tap, '(?m)^# skipped\s+(\d+)')
        if ($matchPass.Success -and $matchFail.Success) {
            $stage.pass=[int]$matchPass.Groups[1].Value
            $stage.fail=[math]::Max($stage.fail,[int]$matchFail.Groups[1].Value)
            if ($matchSkip.Success) {$stage.skip=[int]$matchSkip.Groups[1].Value}
        } else {
            $stage.pass=0; $stage.fail=1; $stage.reason="Missing TAP result summary"
        }
        Set-Location (Join-Path $Root "frontend")
        Invoke-Check "typescript" { & .\node_modules\.bin\tsc.cmd -b }
        Invoke-Check "lint" { & npm.cmd run lint }
        $lintStage = $Results | Where-Object name -eq "lint"
        $lintStage.warnings = @((Get-Content -LiteralPath (Join-Path $Run "lint.log")) | Select-String ': warning ').Count
        Invoke-Check "build" { & npm.cmd run build }
        Set-Location $Root
        if (Test-Path frontend/scripts/test_step4_browser.mjs) {
            if (!$Browser) {
                $Browser = @("$env:ProgramFiles/Google/Chrome/Application/chrome.exe", "${env:ProgramFiles(x86)}/Microsoft/Edge/Application/msedge.exe") |
                    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
            }
            if ($Browser) {
              foreach ($browserStage in @("browser-e2e", "agent-browser-e2e", "grab-browser-e2e", "roi-browser-e2e", "vision-browser-e2e")) {
                $extraArguments = @()
                if ($browserStage -eq "agent-browser-e2e") { $extraArguments = @("--agent") }
                if ($browserStage -eq "grab-browser-e2e") { $extraArguments = @("--grab") }
                if ($browserStage -eq "roi-browser-e2e") { $extraArguments = @("--roi") }
                if ($browserStage -eq "vision-browser-e2e") { $extraArguments = @("--vision") }
                Invoke-Check $browserStage { & node frontend/scripts/test_step4_browser.mjs $Browser (Join-Path $Run $browserStage) @extraArguments }
                $browserLines = Get-Content -LiteralPath (Join-Path $Run ($browserStage + ".log"))
                $hasBrowserSummary = $false
                foreach ($browserLine in $browserLines) {
                    if ($browserLine -notmatch '^\{') { continue }
                    try { $browserResult = $browserLine | ConvertFrom-Json } catch { continue }
                    if ($browserResult.stage -eq "frontend-browser" -and $browserResult.PSObject.Properties.Name -contains "passed") {
                        $hasBrowserSummary = $true
                        $stage = $Results | Where-Object name -eq $browserStage
                        $stage.pass = [int]$browserResult.passed
                        $stage.fail = [math]::Max($stage.fail, [int]$browserResult.failed)
                        $stage.skip = [int]$browserResult.skipped
                    }
                }
                if (!$hasBrowserSummary) {
                    $stage = $Results | Where-Object name -eq $browserStage
                    $stage.pass=0; $stage.fail=1; $stage.reason="Missing browser result summary"
                }
              }
            } else {
                Add-Result "browser-e2e" 0 0 1 "Installed Chrome/Edge not found; no download"
                Add-Result "agent-browser-e2e" 0 0 1 "Installed Chrome/Edge not found; no download"
                Add-Result "grab-browser-e2e" 0 0 1 "Installed Chrome/Edge not found; no download"
                Add-Result "roi-browser-e2e" 0 0 1 "Installed Chrome/Edge not found; no download"
                Add-Result "vision-browser-e2e" 0 0 1 "Installed Chrome/Edge not found; no download"
            }
        } else {
            Add-Result "browser-e2e" 0 0 1 "Safe isolated browser harness unavailable"
            Add-Result "agent-browser-e2e" 0 0 1 "Safe isolated browser harness unavailable"
            Add-Result "grab-browser-e2e" 0 0 1 "Safe isolated browser harness unavailable"
            Add-Result "roi-browser-e2e" 0 0 1 "Safe isolated browser harness unavailable"
            Add-Result "vision-browser-e2e" 0 0 1 "Safe isolated browser harness unavailable"
        }
    }
} catch {
    Add-Result "runner" 0 1 0 $_.Exception.GetType().Name
} finally {
    Set-Location $Root
    if ($Python -and (Test-Path (Join-Path $Run "protected-before.json"))) {
        Invoke-Check "operational-assets" { & $Python -B scripts/safe_regression_backend.py verify --output $Run }
    }
    $safetyPath = Join-Path $Run "safety.json"
    if (Test-Path -LiteralPath $safetyPath) {
        $safety = Get-Content -LiteralPath $safetyPath -Raw | ConvertFrom-Json
        $backendStage = $Results | Where-Object name -eq "backend"
        $backendStage.warnings = [int]$safety.warnings
        Write-Host "Real Gemini API calls: $($safety.real_gemini_api_calls); actual PatchCore predictions: $($safety.real_prediction); checkpoint loads: $($safety.real_load)"
    } else { Add-Result "offline-safety" 0 1 0 "Safety evidence unavailable; real call counts NOT VERIFIED" }
    $Results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Run "summary.json") -Encoding UTF8
    Set-Location $InitialLocation
    $env:PYTHONDONTWRITEBYTECODE = $OriginalBytecode
}

$Failures = ($Results | Measure-Object -Property fail -Sum).Sum
$Skips = ($Results | Measure-Object -Property skip -Sum).Sum
$Results | Format-Table name,pass,fail,skip,warnings,reason -AutoSize | Out-Host
Write-Host "Evidence: $Run"
if ($Failures -gt 0) { Write-Host "SAFE REGRESSION: FAIL"; exit 1 }
if ($Skips -gt 0) { Write-Host "SAFE REGRESSION: PASS WITH SKIP"; exit 0 }
Write-Host "SAFE REGRESSION: PASS"
exit 0
