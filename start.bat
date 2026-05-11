@echo off
cd /d "%~dp0backend"
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
echo ClipFlow 自动视频剪辑工具正在启动...
echo 浏览器打开 http://localhost:8000
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON=python
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON=python3
    ) else (
        echo [错误] 未找到 Python，请先安装 Python 3.9+
        echo 下载地址：https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

REM Check FFmpeg
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [警告] 未找到 ffmpeg，视频处理功能将不可用
    echo 下载地址：https://ffmpeg.org/download.html
    echo 下载后请将 bin 目录添加到系统 PATH 环境变量
    echo.
)

echo 如果没有装依赖，请先运行：%PYTHON% -m pip install -r requirements.txt
echo.
echo 启动中... 浏览器打开 http://localhost:8000
echo.
%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
