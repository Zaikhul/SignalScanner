<#
.SYNOPSIS
    Signal Scanner Unified Launcher for PowerShell
.DESCRIPTION
    Launches FastAPI Backend, Collector Daemon, and Next.js Frontend simultaneously.
.EXAMPLE
    .\run.ps1
    .\run.ps1 --mock
    .\run.ps1 --mode bluetooth
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassthroughArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check Python availability
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python 3 was not found in your PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from python.org or Microsoft Store." -ForegroundColor Yellow
    Exit 1
}

# Run the master orchestrator
python run.py @PassthroughArgs
