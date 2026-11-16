@echo off
title Customer Complaint Triage Graph - Web UI
cd /d "%~dp0"
echo Starting Customer Complaint Triage Graph Web Interface...
python run_ui.py
pause
