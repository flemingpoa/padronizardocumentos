@echo off
chcp 65001 >nul
title Prumo - Padronizacao de documentos
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparando o ambiente pela primeira vez. Isso pode levar alguns minutos...
  py -3.12 -m venv .venv 2>nul || "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)
echo.
echo  Prumo esta iniciando...
echo  Acesse no navegador:  http://127.0.0.1:8000
echo  Para encerrar, feche esta janela.
echo.
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
