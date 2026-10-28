@echo off
title Tutup BAPETEN Evaluator
color 0c
cls
echo ================================================================
echo        MENUTUP KONEKSI BAPETEN EVALUATOR
echo ================================================================
echo.
echo Menghentikan koneksi tunnel ke HPC...

:: Cari PID proses yang listening di port 8001 lalu hentikan
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [OK] Koneksi telah ditutup.
timeout /t 2 >nul
exit
