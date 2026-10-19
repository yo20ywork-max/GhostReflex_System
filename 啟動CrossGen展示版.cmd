@echo off
setlocal
set "CROSSGEN_DEMO=%~dp0delivery\meeting-20260907\brand-dist\CrossGen-AGI-mu\CrossGen-AGI-mu.exe"
if not exist "%CROSSGEN_DEMO%" (
  echo CrossGen demonstration executable was not found.
  echo Download and extract the complete Windows archive from:
  echo https://huggingface.co/yoxia/CrossGen-AGI-mu-v0.1
  pause
  exit /b 1
)
start "" "%CROSSGEN_DEMO%"
