@echo off
rem Resume the experiment: start the load generator (if not running) and the campaign as
rem independent background processes. Usage, from the project folder:  scripts\resume.cmd
cd /d "%~dp0.."
if not exist logs\loadgen.pid powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1 loadgen
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1 campaign
