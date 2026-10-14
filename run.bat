@echo off
rem 后台启动桌面切换面板（无控制台窗口）
setlocal
cd /d "%~dp0"

set PY=
if exist "%VIRTUAL_ENV%\Scripts\pythonw.exe" set PY=%VIRTUAL_ENV%\Scripts\pythonw.exe

if "%PY%"=="" (
    for /f "delims=" %%i in ('where pythonw 2^>nul') do (
        set PY=%%i
        goto found
    )
)
:found
if "%PY%"=="" (
    echo 没找到 pythonw，请先安装 Python 并加入 PATH，或激活虚拟环境后重试。
    pause
    exit /b 1
)

start "" "%PY%" "%~dp0main.py"
endlocal
