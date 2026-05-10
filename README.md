# ClipFlow — 自动视频剪辑工具

基于 AI 语音识别与自然语言理解，把「视频剪辑」变成「对话」。零学习成本，十分钟出片。

> 上传视频 → AI 自动转写 + 识别说话人 → 用大白话告诉 AI 保留哪些内容 → 一键导出

## 核心功能

- **多语言语音转写** — faster-whisper，支持中英日韩等 99 种语言，VAD 静音过滤，1 分钟视频 ~3 秒完成
- **说话人分离** — pyannote.audio speaker-diarization-3.1，自动区分不同说话人，支持双击改名
- **AI 多轮对话剪辑** — DeepSeek 大模型语义理解，用大白话描述需求（如「保留讲产品优势的部分」），AI 自动匹配段落
- **关键词搜索 + 视频跳转** — 输入关键词高亮匹配段，回车跳转视频对应时刻，上下箭头快速导航
- **三种导出方式** — 拼接 MP4 / 字幕烧录 / SRT 字幕文件（可导入 Premiere、Final Cut Pro、DaVinci Resolve）
- **开机自启** — macOS launchd 后台服务，开机自动启动，崩溃自动恢复

## 快速开始

### 环境要求

- macOS 10.15+
- Python 3.9+
- FFmpeg

### 1. 克隆项目

```bash
git clone https://github.com/baidonghui1055224505-sudo/ClipFlow.git
cd ClipFlow
```

### 2. 安装依赖

```bash
pip3 install -r backend/requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
# backend/.env
DEEPSEEK_API_KEY=sk-your-deepseek-key
HF_TOKEN=hf-your-huggingface-token  # 可选，说话人分离功能需要
```

> 获取 DeepSeek API Key：https://platform.deepseek.com/api_keys
> 获取 HuggingFace Token：https://huggingface.co/settings/tokens

#### API 费用说明

| 功能 | 是否必需 | 费用 | 说明 |
|------|:--:|------|------|
| 语音转写 | 必装 | **免费** | 本地 Whisper 模型，离线可用 |
| AI 对话剪辑 | 推荐 | **DeepSeek API 按量计费** | 约 ¥1/百万字，每次对话剪辑几分钱，充值 10 元够用很久 |
| 说话人分离 | 可选 | **免费** | HF Token 免费申请，模型本地运行 |

> 不配 API Key 也可用：上传视频 → 转写 → 手动点选段落 → 导出。只是没有 AI 帮你自动选。

### 4. 启动服务

```bash
./start.sh
```

然后浏览器打开 **http://localhost:8000**

### 5. 开机自启（可选）

```bash
# 编辑 plist 中的路径和 token
cp com.autovideo.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.autovideo.server.plist
```

## 技术架构

```
浏览器 (单页 HTML)
      ↓ HTTP / REST API
FastAPI + Uvicorn (异步 Web 服务)
      ↓ 调用
┌─────────────────────────────────┐
│ faster-whisper    语音转写  CPU │
│ pyannote.audio    说话人分离    │
│ DeepSeek Chat     语义理解      │
│ FFmpeg            视频处理      │
└─────────────────────────────────┘
      ↓ 持久化
本地文件系统 (临时文件 + 会话内存)
```

## 使用流程

1. 上传视频文件或粘贴视频链接（支持 B站 / YouTube）
2. 可选：勾选「说话人分离」、选择转写精度（tiny 快速 / medium 高精度）
3. 点击「开始转写」
4. 在 AI 对话面板用大白话描述需求，如：
   - 「只保留讲产品优势的部分」
   - 「去掉开场寒喧」
   - 「保留嘉宾B关于技术的发言」
5. 手动微调选中段落
6. 导出：拼接视频 / 带字幕导出 / SRT 字幕文件

## 业务场景

| 场景 | 说明 |
|------|------|
| 自媒体/短视频 | AI 对话筛选精彩片段，说话人分离适合多人访谈 |
| 企业内部会议 | 自动生成带时间戳文字稿 + 说话人标签，快速定位关键讨论 |
| 教育培训 | 筛选重点知识点拼接精华版，搜索关键词跳转对应位置 |
| 用户访谈 | 区分主持人和受访者发言，快速定位有价值观点 |
| 播客制作 | 去掉口误、空白、跑题段落，比手动剪辑高效 10 倍 |

## 项目结构

```
ClipFlow/
├── backend/
│   ├── main.py              # FastAPI 主服务
│   ├── transcriber.py       # faster-whisper 语音转写
│   ├── speaker_diarize.py   # pyannote 说话人分离
│   ├── ai_selector.py       # DeepSeek 对话剪辑
│   ├── video_processor.py   # FFmpeg 视频处理
│   └── requirements.txt     # Python 依赖
├── frontend/
│   └── index.html           # 单页前端（无框架依赖）
├── start.sh                 # 启动脚本
└── README.md
```
