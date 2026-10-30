@echo off
rem Glisser le dossier du vol (vols\entrant\mission_XXXXX_NN) sur ce fichier.
if "%~1"=="" (
  echo Usage : glisser le dossier du vol sur analyser.bat, ou : analyser.bat DOSSIER_DU_VOL
  pause
  exit /b 1
)
if not defined DRONE_DATA_DIR set "DRONE_DATA_DIR=%~dp0..\..\..\data"
call "%~dp0outils\env_python.bat" || (pause & exit /b 1)
"%PY%" "%~dp0pipeline.py" "%~1"
if %ERRORLEVEL%==0 for /f "delims=" %%r in ('dir /b /ad /o-d "%DRONE_DATA_DIR%\vols\20*"') do (start "" "%DRONE_DATA_DIR%\vols\%%r\rapport.html" & goto :fin)
:fin
pause
