@echo off
rem Double-cliquez sur ce fichier : il sert la racine du depot sur http://localhost:8001
rem et ouvre la page des exercices web (Chrome ou Edge).
cd /d "%~dp0..\.."
where py >nul 2>nul && (py planificateur\serveur_local.py 8001 --racine . --page tp/exercices_web/ & goto :fin)
where python >nul 2>nul && (python planificateur\serveur_local.py 8001 --racine . --page tp/exercices_web/ & goto :fin)
echo Python est introuvable. Installez-le (https://www.python.org/downloads/ ou "winget install Python.Python.3.12")
echo puis relancez ce fichier.
pause
:fin
