#!/bin/bash
cd "$(dirname "$0")/backend"
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
echo "自动视频剪辑工具已启动"
echo "浏览器打开 http://localhost:8000"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
