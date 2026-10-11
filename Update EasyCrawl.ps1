param([switch]$CheckOnly, [int]$WaitForPid = 0)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Run-Git {
    param([string[]]$Arguments)
    $result = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($result -join "`n") }
    return $result
}
try {
    if ($WaitForPid -gt 0) {
        Write-Host 'Waiting for EasyCrawl to close...'
        $appProcess = Get-Process -Id $WaitForPid -ErrorAction SilentlyContinue
        if ($appProcess) { $appProcess | Wait-Process }
    }
    Write-Host 'EasyCrawl updater'
    Write-Host 'Close EasyCrawl before updating.'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not available. Install Git for Windows first.' }
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'The local Python environment is missing. Set up .venv before updating.' }
    $changes = @(Run-Git -Arguments @('status', '--porcelain'))
    if ($changes.Count -gt 0) {
        Write-Host ($changes -join "`n")
        throw 'Local changes were found. Commit and push them, or move unrelated files out of this folder, before updating. No files were changed.'
    }
    $branch = Run-Git -Arguments @('symbolic-ref', '--quiet', '--short', 'HEAD')
    $upstream = Run-Git -Arguments @('rev-parse', '--abbrev-ref', '@{upstream}')
    Write-Host "Branch: $branch | Updates from: $upstream"
    if ($CheckOnly) { Write-Host 'Checks passed. No update was performed.'; exit 0 }
    $before = Run-Git -Arguments @('rev-parse', 'HEAD')
    Run-Git -Arguments @('pull', '--ff-only') | ForEach-Object { Write-Host $_ }
    Write-Host 'Refreshing dependencies...'
    & $python -m pip install -e '.[ui,dev]' imageio-ffmpeg
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. The Git update may already have completed. Check the message above and run this updater again after resolving the problem.' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed. Check the message above.' }
    $after = Run-Git -Arguments @('rev-parse', 'HEAD')
    if ($before -eq $after) { Write-Host 'EasyCrawl was already current. Dependencies are ready.' }
    else { Write-Host 'EasyCrawl updated successfully. You can reopen the app.' }
    exit 0
} catch {
    Write-Host "`nUpdate stopped: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'The updater never discards, resets, or stashes your local work.'
    exit 1
}
