@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" pythonw wechat_voice_web.py
exit
