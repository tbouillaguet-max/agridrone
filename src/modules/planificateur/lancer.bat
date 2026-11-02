@echo off
rem Double-cliquez sur ce fichier : il sert le planificateur sur http://localhost:8000
rem et l'ouvre dans le navigateur (utilisez Chrome ou Edge pour le câble USB vers AU2).
rem Les missions envoyées sont archivées dans data\missions.
cd /d "%~dp0"
where py >nul 2>nul && (py serveur_local.py & goto :fin)
where python >nul 2>nul && (python serveur_local.py & goto :fin)
echo Python est introuvable. Installez-le (https://www.python.org/downloads/ ou "winget install Python.Python.3.12")
echo puis relancez ce fichier.
pause
:fin
