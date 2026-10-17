<#
.SYNOPSIS
    Signal Scanner Multi-Pane Terminal Launcher
.DESCRIPTION
    Uses Windows Terminal (wt.exe) to split the terminal into 3 interactive side-by-side panes:
    - Left: Backend (FastAPI :8000)
    - Middle: Collector (Daemon :8001)
    - Right: Frontend (Next.js :3000)
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check if wt.exe (Windows Terminal) is available
if (Get-Command wt.exe -ErrorAction SilentlyContinue) {
    Write-Host "[INFO] Launching 3 split panes in Windows Terminal..." -ForegroundColor Cyan

    # Dynamic port determination via Python helper
    $backendPort = python -c "from run import resolve_available_port; print(resolve_available_port(8000, [8888, 9000, 8500], 'Backend'))" 2>$null
    if (-not $backendPort) { $backendPort = "8888" }

    $backendCmd = "pwsh -NoExit -Command `"cd '$ScriptDir'; uvicorn app.main:app --app-dir backend --reload --port $backendPort`""
    $collectorCmd = "pwsh -NoExit -Command `"cd '$ScriptDir'; python -m collector.app.main --mode wifi --backend-url http://127.0.0.1:$backendPort`""
    $frontendCmd = "pwsh -NoExit -Command `"cd '$ScriptDir\frontend'; `$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:$backendPort'; pnpm dev`""

    & wt.exe -w 0 nt -d "$ScriptDir" --title "Signal Scanner - Backend (:$backendPort)" $backendCmd `; `
             split-pane -H -d "$ScriptDir" --title "Signal Scanner - Collector" $collectorCmd `; `
             split-pane -V -d "$ScriptDir\frontend" --title "Signal Scanner - Frontend" $frontendCmd
} else {
    Write-Host "[WARN] Windows Terminal (wt.exe) not found. Falling back to unified runner..." -ForegroundColor Yellow
    & "$ScriptDir\run.ps1"
}
