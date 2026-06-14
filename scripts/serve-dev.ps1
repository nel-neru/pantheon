# Pantheon - DEV environment launcher.
#
# Development/testing data is FULLY ISOLATED in ~/.pantheon-dev via PANTHEON_HOME, so dev work
# (self-improvement Meta org, evolve loops, experiments) never pollutes the user's real data.
# Port: 7870.  Data: %USERPROFILE%\.pantheon-dev
# First-time setup: run scripts\init-dev.ps1 once (or: $env:PANTHEON_HOME=...; python main.py init).
# Friendly URL: http://dev.pantheon.localhost:7870  (*.localhost auto-resolves to 127.0.0.1)
$ErrorActionPreference = "Stop"
$env:PANTHEON_HOME = Join-Path $HOME ".pantheon-dev"
$env:PANTHEON_ENV = "development"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "[Pantheon] DEV env   | home=$env:PANTHEON_HOME | http://dev.pantheon.localhost:7870"
& "$root\.venv\Scripts\python.exe" "$root\main.py" serve --port 7870
