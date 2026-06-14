# Pantheon - USER (production) environment launcher.
#
# The real, user-facing data lives in the DEFAULT platform home (~/.pantheon).
# This launcher explicitly clears PANTHEON_HOME so the user env never reads dev data.
# Port: 7860.  Data: %USERPROFILE%\.pantheon
$ErrorActionPreference = "Stop"
Remove-Item Env:PANTHEON_HOME -ErrorAction SilentlyContinue
$root = Split-Path -Parent $PSScriptRoot
Write-Host "[Pantheon] USER env  | home=$HOME\.pantheon | http://localhost:7860"
& "$root\.venv\Scripts\python.exe" "$root\main.py" serve --port 7860
