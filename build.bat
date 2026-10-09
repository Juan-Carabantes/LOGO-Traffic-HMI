@echo off
rem --- Crea dist\LOGO-Traffic-HMI.exe (un solo archivo, no requiere Python) ---
chcp 65001 >nul
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo No se encontro el entorno venv. Crea el entorno e instala requirements.txt primero.
    pause
    exit /b 1
)

echo [1/3] Instalando PyInstaller...
venv\Scripts\python.exe -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib || goto error

echo [2/3] Preparando modelos de IA (descarga y OpenVINO; solo la primera vez)...
venv\Scripts\python.exe packaging\prepare_models.py || goto error

echo [3/3] Creando el .exe (puede tardar 10-20 minutos)...
venv\Scripts\python.exe -m PyInstaller --noconfirm --clean LOGO-Traffic-HMI.spec || goto error

echo.
echo Listo: %~dp0dist\LOGO-Traffic-HMI.exe
explorer dist
pause
exit /b 0

:error
echo.
echo Ocurrio un error. Revisa los mensajes de arriba.
pause
exit /b 1
