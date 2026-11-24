@echo off
title Share Customer Complaint Triage Graph - Public HTTPS Tunnel
echo ======================================================================
echo   CREATING INSTANT PUBLIC HTTPS LINK FOR YOUR TRIAGE WEB APP
echo ======================================================================
echo.
echo Make sure start_web.bat is currently running in another window!
echo.
echo Launching public tunnel on port 8000 via localtunnel...
echo.
npx --yes localtunnel --port 8000
pause
