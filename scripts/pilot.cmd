@echo off
rem Steady state followed by the pilot campaign (3 windows, 1 repetition), as one background job.
rem Start with:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 pilot
cd /d "%~dp0.."
".venv\Scripts\lambda-rca.exe" steady-state --minutes 30
".venv\Scripts\lambda-rca.exe" campaign --only W002,W005,W007 --reps 1
echo PILOT FINISHED
