@echo off
rem Prepare l'environnement Python du projet (drone-workflow) et definit PY.
rem Cree l'environnement s'il n'existe pas, puis installe requirements.txt.
set "VENV=%USERPROFILE%\drone-workflow"
set "PY=%VENV%\Scripts\python.exe"
if exist "%PY%" goto :deps
set BASE=
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set BASE="%%d\python.exe"
if not defined BASE for /d %%d in ("C:\Program Files\Python3*") do if exist "%%d\python.exe" set BASE="%%d\python.exe"
if not defined BASE (
  echo [ECHEC] aucun Python systeme trouve pour creer %VENV%
  exit /b 1
)
echo Creation de l'environnement %VENV% avec %BASE%
%BASE% -m venv "%VENV%" || exit /b 1
"%PY%" -m pip install -q --upgrade pip
:deps
"%PY%" -m pip install -q -r "%~dp0..\requirements.txt" || exit /b 1
exit /b 0
