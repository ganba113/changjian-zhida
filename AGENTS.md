# AGENTS.md — 昌检智答 AI 助手

面向检察机关的 AI Agent 智能问答平台。已上线运行。

## 项目概述

- 浏览器 → FastAPI(80 端口，同时托管前端 dist) → vLLM(8000 端口)。
- 对话历史、知识库文档、向量全部存 SQLite（`backend/chat.db`）。
- 部署环境是**离线内网 aarch64 服务器**，本机（Windows/x86）无法完整联调后端。

## 技术栈与目录

| 层 | 技术 | 位置 |
|----|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Element Plus | `frontend/changjian-zhida/` |
| 后端 | FastAPI + SQLite（单文件 `backend/main.py`） | `backend/` |
| 模型 | vLLM + Qwen（OpenAI 兼容接口） | 远程服务器 |
| 部署 | systemd + 离线 wheel 打包 | `deploy/` |

## Setup / 开发命令

```bash
# 前端（本机 Windows，用 node 直接调 vite，避免 npm 脚本 .ps1 问题）
cd frontend/changjian-zhida
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit   # 类型检查
node node_modules/vite/bin/vite.js build            # 构建到 frontend/changjian-zhida/dist

# 打包部署包（含 backend + dist + deploy，排除 chat.db/.env/.pyc）
python deploy_package.py

# 后端语法检查（本机 python 3.13 无 fastapi，只能做语法检查，不能 import 运行）
python -m py_compile backend/main.py
```

## 关键约束（务必遵守，否则会踩坑）

1. **本机无法跑后端**：`backend/wheels/` 里是 aarch64+py39 的 wheel，本机 Python 3.13 装不上。后端逻辑改动只能 `py_compile` 做语法检查，完整联调在服务器做。
2. **服务器环境**：openEuler 22.03 aarch64、Python 3.9.9、无公网、无 nginx（后端直接托管 dist）。
3. **数据安全**：所有数据在 `backend/chat.db`。**重新部署严禁 `rm -rf`**，用 `unzip -o` 覆盖（部署包已排除 chat.db/.env）。
4. **版本锁定勿动**（aarch64+py39 兼容性）：numpy 1.24.4、onnxruntime 1.15.1、tokenizers 0.13.3、protobuf 3.20.3、opencv-headless 4.9.0.80、shapely 2.0.5、PyMuPDF 1.26.0。升级会破坏离线部署。
5. **Qwen 思考模式必须关**：请求带 `chat_template_kwargs={"enable_thinking": false}`，否则输出英文思考过程。
6. **前端无 markdown 渲染**：MessageList 用 `white-space: pre-wrap` 纯文本渲染，system prompt 里用 `OUTPUT_FORMAT_NOTICE` 约束模型输出纯文本，别去掉。
7. **jieba 是 vendor 内嵌源码**（`backend/vendor/jieba/`，`sys.path` 注入），不 pip 安装、不写 requirements。
8. **BM25 用 `jieba.lcut_for_search`**（不是 `lcut`），否则「盗窃罪」等词召回失败。

## OCR 模块（RapidOCR 方案）

- 后端可插拔引擎：tesseract → rapidocr → paddleocr 探测，`/api/ocr/status` + `/api/ocr`。
- 默认用 RapidOCR（onnxruntime 后端），`rapidocr_onnxruntime==1.4.4` 内置 PP-OCRv4 模型，离线开箱即用。
- PDF 分流：文字型直接 `get_text()`，扫描型逐页 `get_pixmap(dpi=200)` 渲染喂 RapidOCR。
- **OCR 依赖安装必须 `--no-deps`**：rapidocr 声明依赖 `opencv-python`，本项目用 `opencv-python-headless` 替代，二者是不同包名，pip 无法自动替代，不加 `--no-deps` 会报错。

## 质量门槛（改完代码必须做）

- 前端改动：跑 `vue-tsc --noEmit` + `vite build`，确认产物进 `dist/`。
- 后端改动：跑 `python -m py_compile backend/main.py`。
- 需要部署时：跑 `python deploy_package.py` 重新打包 `changjian-zhida-deploy.zip`。
- 新增 Python 依赖：只允许纯 Python 源码内嵌 vendor，或跨平台下载 aarch64+py39 的 wheel（用阿里云镜像 `--platform manylinux_2_17_aarch64 --python-version 39`）。

## 禁止事项

- 不要删除 `.workbuddy/` 目录（项目数据，非缓存）。
- 不要提交 `.env`、`chat.db`、wheels、模型文件、安装包到 git。
- 不要改依赖版本号（见「版本锁定勿动」）。
