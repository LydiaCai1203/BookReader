# 📚 BookReader

> 一款轻量级 EPUB 阅读器 Web 应用，支持文字阅读与 AI 语音朗读

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

### 💰 完全免费

当前版本使用 **Microsoft Edge TTS** 引擎，无需 API Key，无需付费，完全白嫖微软的高质量语音合成服务！

---

## ✨ 功能亮点

| 功能 | 描述 |
|------|------|
| 📖 **文字阅读** | 智能分句、章节导航、阅读进度追踪 |
| 🎧 **在线语音** | 基于 Microsoft Edge TTS，14+ 种中文音色可选 |
| 🎯 **逐词高亮** | 播放时实时高亮当前朗读的词语 |
| ⚡ **音频缓存** | 已生成的音频自动缓存，无需重复生成 |
| 📥 **离线下载** | 支持整本书音频下载，断点续传 |
| 📚 **书架管理** | 上传的书籍自动保存，随时继续阅读 |

---

## 🛠️ 技术栈

### 后端 (Backend)

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 运行环境 |
| **FastAPI** | Web 框架，高性能异步 API |
| **edge-tts** | 微软 Edge TTS 引擎，免费语音合成 |
| **ebooklib** | EPUB 文件解析 |
| **BeautifulSoup4** | HTML 内容提取 |
| **langdetect** | 自动语言检测 |

### 前端 (Frontend)

| 技术 | 用途 |
|------|------|
| **React 18** | UI 框架 |
| **TypeScript** | 类型安全 |
| **Vite** | 构建工具 |
| **TailwindCSS** | 样式框架 |
| **shadcn/ui** | UI 组件库 |
| **TanStack Query** | 数据请求管理 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- pnpm / npm

### 1. 启动后端

```bash
cd epub-tts-backend

# 创建虚拟环境（首次）
python -m venv venv

# 激活虚拟环境
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 启动前端

```bash
cd epub-tts-frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 3. 访问应用

打开浏览器访问 [http://localhost:5173](http://localhost:5173)

---

## 📁 项目结构

```
ett/
├── epub-tts-backend/          # 后端服务
│   ├── app/
│   │   ├── main.py            # 应用入口
│   │   ├── api.py             # API 路由
│   │   └── services/          # 业务逻辑
│   │       ├── book_service.py    # 书籍管理
│   │       ├── tts_service.py     # 语音合成
│   │       └── task_service.py    # 后台任务
│   └── data/                  # 数据存储（已 gitignore）
│       ├── books/             # 上传的 EPUB 文件
│       ├── audio/             # 生成的音频缓存
│       └── covers/            # 书籍封面
│
└── epub-tts-frontend/         # 前端应用
    └── src/
        ├── components/        # UI 组件
        ├── api/               # API 服务层
        └── pages/             # 页面组件
```

---

## 🎨 界面预览

<!-- 可以添加截图 -->
<!-- ![首页](./screenshots/home.png) -->
<!-- ![阅读页](./screenshots/reader.png) -->

---

## 🗺️ Roadmap

### 已完成 ✅

- [x] EPUB 解析与阅读
- [x] Microsoft Edge TTS 语音合成（免费）
- [x] 多种中文音色选择
- [x] 逐词高亮跟读
- [x] 音频缓存与离线下载
- [x] 断点续传
- [x] 书架管理

### 计划中 🚧

- [ ] **多语言支持** - 外语书籍阅读
- [ ] **LLM 智能翻译** - 接入大语言模型，实时翻译外语内容
- [ ] **高级语音引擎** - 支持更多 TTS 服务商
  - [ ] OpenAI TTS
  - [ ] Azure Speech
  - [ ] ElevenLabs
  - [ ] Fish Audio
- [ ] **流行音色** - 支持更自然、更有表现力的 AI 音色
- [ ] **语音克隆** - 自定义音色
- [ ] **PDF 支持** - 扩展文档格式支持

---

## 📝 License

MIT License © 2024

---

## 🤝 Contributing

欢迎提交 Issue 和 Pull Request！
