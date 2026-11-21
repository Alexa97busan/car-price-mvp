@echo off
cd /d "%~dp0"
start "car-price-server" /min cmd /c "python -m http.server 8123"
timeout /t 2 >nul
start "" "http://127.0.0.1:8123/"
