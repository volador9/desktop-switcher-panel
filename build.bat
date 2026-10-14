@echo off
rem 打包为单文件 exe：dist\DesktopSwitcherPanel.exe
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (
    echo 没找到 python，请先安装 Python 并加入 PATH。
    pause
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name DesktopSwitcherPanel ^
  --add-binary "VirtualDesktopAccessor.dll;." ^
  main.py

echo.
echo 完成：%~dp0dist\DesktopSwitcherPanel.exe
pause
endlocal
