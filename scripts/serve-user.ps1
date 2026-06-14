# Pantheon - USER (production) environment launcher.
#
# The real, user-facing data lives in the DEFAULT platform home (~/.pantheon).
# This launcher explicitly clears PANTHEON_HOME so the user env never reads dev data.
# Port: 7860.  Data: %USERPROFILE%\.pantheon
# Friendly URL: http://pantheon.localhost:7860  (*.localhost auto-resolves to 127.0.0.1)
$ErrorActionPreference = "Stop"
Remove-Item Env:PANTHEON_HOME -ErrorAction SilentlyContinue
$env:PANTHEON_ENV = "production"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "[Pantheon] USER (PROD) | home=$HOME\.pantheon | http://pantheon.localhost:7860"
& "$root\.venv\Scripts\python.exe" "$root\main.py" serve --port 7860
