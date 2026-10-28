@echo off
title BAPETEN AI Evaluator — Penghubung Sistem
color 1f
cls
echo ================================================================
echo        BAPETEN — ASISTEN EVALUASI PERIZINAN (HPC)
echo ================================================================
echo.
echo Menghubungkan ke server HPC BAPETEN...
echo Pastikan VPN BAPETEN di laptop Anda sudah terhubung (AKTIF).
echo.

:: Pastikan izin file kunci aman untuk Windows OpenSSH
icacls "%~dp0bapeten_key" /inheritance:r /grant:r "%USERNAME%:(R)" >nul 2>&1

:: Cek apakah port 8001 sudah aktif / pernah dibuka sebelumnya
netstat -ano | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Koneksi evaluator sudah aktif!
    echo Membuka browser...
    start http://localhost:8001/
    timeout /t 3 >nul
    exit
)

:: Jalankan koneksi SSH tunnel di background
start /min "BAPETEN_TUNNEL" ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=NUL -i "%~dp0bapeten_key" -N -L 8001:127.0.0.1:8001 fajar@192.168.30.75

echo Menunggu koneksi siap...
timeout /t 3 /nobreak >nul

:: Verifikasi apakah tunnel berhasil terbentuk
netstat -ano | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [PERHATIAN] Belum dapat terhubung ke server HPC.
    echo Pastikan:
    echo 1. VPN BAPETEN di laptop Anda sudah menyala / terhubung.
    echo 2. Jaringan internet Anda stabil.
    echo.
    pause
    exit
)

echo.
echo [BERHASIL] Terhubung ke Asisten Evaluasi Perizinan BAPETEN!
echo Membuka aplikasi di browser Anda...
start http://localhost:8001/
timeout /t 3 >nul
exit
