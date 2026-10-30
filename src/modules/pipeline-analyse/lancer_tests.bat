@echo off
rem Lance les tests du pipeline dans l'environnement drone-workflow ; resultat dans tests_windows.log
cd /d "%~dp0"
> tests_windows.log echo === %DATE% %TIME%
call outils\env_python.bat >> tests_windows.log 2>&1
if errorlevel 1 (
  >> tests_windows.log echo ECHEC_ENVIRONNEMENT
  goto :fin
)
>> tests_windows.log echo PY=%PY%
"%PY%" -c "import sys, platform; print(sys.version); print(sys.prefix); print(platform.platform())" >> tests_windows.log 2>&1
"%PY%" -m pytest -q -p no:cacheprovider tests >> tests_windows.log 2>&1
>> tests_windows.log echo CODE_TESTS=%ERRORLEVEL%
"%PY%" outils\creer_vol_demo.py --alerte-critique >> tests_windows.log 2>&1
"%PY%" pipeline.py demo\vols\entrant\mission_09001_01 --missions demo\missions --sortie demo\vols --modeles modeles_demo.json --silencieux >> tests_windows.log 2>&1
>> tests_windows.log echo CODE_DEMO=%ERRORLEVEL%
:fin
>> tests_windows.log echo === FIN
