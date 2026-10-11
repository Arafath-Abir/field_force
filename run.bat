@echo off
title Field Force Management - Odoo 14
echo ======================================================
echo Starting Field Force Management Project
echo ======================================================

REM 1. Ensure PostgreSQL is running
"C:\Users\Public\PostgreSQL\bin\pg_ctl.exe" status -D "C:\Users\Public\PostgreSQL\data" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Starting PostgreSQL...
    "C:\Users\Public\PostgreSQL\bin\pg_ctl.exe" start -D "C:\Users\Public\PostgreSQL\data" -l "C:\Users\Public\PostgreSQL\postgres.log"
    timeout /t 3 /nobreak >nul
) else (
    echo PostgreSQL is active.
)

REM 2. Launch Field Force Management on Odoo
echo Starting Field Force Management on http://localhost:8069 ...
start http://localhost:8069/web/login
py -3.9 "D:\Software\Odoo\odoo\odoo-bin" -c "%~dp0odoo.conf" -d field_force_db

pause
