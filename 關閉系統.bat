@echo off
chcp 65001 >nul
title GhostReflex 關閉腳本
echo 正在關閉 GhostReflex 與背景行程...
taskkill /f /im python.exe >nul 2>nul
taskkill /f /im GhostReflex.exe >nul 2>nul
echo [完成] 行程已結束。
timeout /t 1 >nul
exit