@echo off
rem Vol de demonstration (modele factice) : pipeline\demo, ne touche pas aux vraies missions.
cd /d "%~dp0"
call outils\env_python.bat || goto :fin
"%PY%" outils\creer_vol_demo.py --alerte-critique || goto :fin
"%PY%" pipeline.py demo\vols\entrant\mission_09001_01 --missions demo\missions --sortie demo\vols --modeles modeles_demo.json
if %ERRORLEVEL%==0 for /f "delims=" %%r in ('dir /b /ad /o-d "demo\vols\20*"') do (start "" "demo\vols\%%r\rapport.html" & goto :fin)
:fin
pause
