@echo off
cd /d "%~dp0backend"
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
echo ClipFlow 自动视频剪辑工具正在启动...
echo 浏览器打开 http://localhost:8000
echo.
echo 如果看到报错，请先安装依赖：pip install -r requirements.txt
echo 如果提示找不到 ffmpeg，请从 https://ffmpeg.org/download.html 下载并添加到 PATH
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
