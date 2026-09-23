# AGENTS.md — 昌检智答 AI 助手

面向检察机关的 AI Agent 智能问答平台。已上线运行（openEuler aarch64 离线内网部署）。

## 项目概述

- 数据流：浏览器 → FastAPI(80 端口，同时托管前端 dist) → vLLM(8000 端口)。
- 所有数据存 SQLite（`backend/chat.db`），对话历史、知识库文档、分块、向量、反馈都在这一个库。
- 部署环境是**离线内网 aarch64 服务器**，本机（Windows/x86）**无法完整联调后端**。

## 技术栈与目录

| 层 | 技术 | 位置 |
|----|------|------|
| 前端 | Vue 3 + TS + Vite + Pinia + Element Plus | `frontend/changjian-zhida/` |
| 后端 | FastAPI + SQLite（**单文件 `backend/main.py`，约 1900 行**） | `backend/` |
| 模型 | vLLM + Qwen（OpenAI 兼容接口） | 远程服务器 |
| 内置依赖 | `vendor/jieba/`（分词源码）、`vendor/bge/`（embedding 模型） | `backend/vendor/` |
| 离线依赖 | `wheels/`（45 个 aarch64+py39 wheel） | `backend/wheels/` |
| 部署 | systemd + 离线打包 | `deploy/` |

## 数据库结构（7 张表，都在 `init_db()` 里建）

| 表 | 关键字段 | 用途 |
|----|---------|------|
| `conversations` | id, user_id, title, create_time, update_time | 会话 |
| `messages` | id, conversation_id, role, content, attachments, create_time | 消息 |
| `kb_libraries` | id, user_id, name, sort_order | 知识库（部门库，`user_id='shared'` 全局共享） |
| `kb_documents` | id, library_id, filename, title, content, char_count, chunk_count | 知识库文档 |
| `kb_chunks` | id, doc_id, idx, content, vec(BLOB) | 文档分块，`vec` 存 float32 向量 |
| `sys_config` | key, value | 运行时配置 + 提示词模板 |
| `feedback` | message_id, conversation_id, rating | 回答点赞/点踩 |

> 表结构兼容旧库迁移：`init_db()` 用 `PRAGMA table_info` 检查缺列后 `ALTER TABLE` 补列。

## 关键函数/常量（改代码前先定位这里）

| 名称 | 位置作用 |
|------|---------|
| `AGENTS` 常量 | 6 个检察智能体（法条检索/案件分析/文书起草/类案参考/证据梳理/程序指引）的 system prompt 字典 |
| `system_prompt_for(agent_id)` | 组装 system prompt = base + identity_notice + output_format_notice |
| `_vllm_deltas(messages)` | 流式转发 vLLM 的公共生成器 |
| `_error_to_sse(e)` | 异常转 SSE 错误事件的公共函数 |
| `_split_chunks(text)` / `_split_fixed(text)` | 知识库分块 |
| `_ARTICLE_RE` | 分条正则 `第[一二三四五六七八九十百千零\d]+条` |
| `_require_admin(pwd)` | 管理员密码校验（`X-Admin-Password` 头） |
| `_PROMPT_OVERRIDES` | 提示词模板内存缓存（启动时从 sys_config 加载） |

## 功能模块实现要点

### 1. 对话（一期核心）
- SSE 流式：`POST /api/chat/completions`，事件类型 `retrieval`/`delta`/`error`，`[DONE]` 结束。
- 终止：前端 AbortController + fetch signal。
- 用户隔离：前端 `localStorage.cj_user_id` → `X-User-Id` 请求头 → 后端按 user_id 过滤。

### 2. 智能体
- `ChatRequest.agent_id` 非空时，`system_prompt_for(agent_id)` 的结果注入 messages[0]。
- 智能体列表 `GET /api/agents` 从 `AGENTS` 常量下发。

### 3. 知识库 RAG（混合检索）
- **分块**：`_split_chunks` 先按 `_ARTICLE_RE`（第X条）切条文，超长再 `_split_fixed` 固定切（KB_CHUNK_SIZE=500，重叠 50），无结构退化固定切。
- **BM25 关键词**：**必须用 `jieba.lcut_for_search`**（不是 `lcut`），否则「盗窃罪」这类词召回失败。
- **向量语义**：BGE-small-zh-v1.5（ONNX INT8，512 维，`vendor/bge/`），onnxruntime 推理；embedding 全部**惰性导入**，缺依赖自动退化为纯 BM25。
- **RRF 融合**：BM25 排名 + 向量排名，倒数排名融合（KB_RRF_K=60）。
- **按部门分库**：12 个默认部门库，`KB_USER='shared'` 所有用户共享；问答下沉到 AI 助手首页（`ChatRequest.library_id` 触发 RAG），知识库页只做文档管理+检索。
- 接口：`/api/kb/libraries`、`/api/kb/libraries/{id}/documents`、`/api/kb/documents/{id}`、`/api/kb/search`、`/api/kb/reindex`（补向量，需管理员密码）。

### 4. OCR（含 PDF 分流）
- 可插拔引擎探测顺序：tesseract → rapidocr → paddleocr（`_ocr_engine()`）。
- 默认 RapidOCR：`rapidocr_onnxruntime==1.4.4` 内置 PP-OCRv4 模型，离线开箱即用。
- `_ocr_array(img, engine)` 是核心复用函数（图片和 PDF 页都走它）。
- `_rapidocr_text()` 兼容旧版 tuple `(result, elapse)` 和新版 `RapidOCROutput` 两种返回。
- **PDF 分流**：`_pdf_text_layer()` 提取文本层，字符数 `>= max(50, 页数*20)` 判定文字型直接返回（无需 OCR）；否则 `_ocr_pdf_scanned()` 逐页 `get_pixmap(dpi=200)` 渲染喂 RapidOCR。

### 5. 系统管理（需管理员密码）
- 统计卡片、近7天柱状图、数据备份（sqlite3 backup API）、vLLM 健康监控、知识库索引状态、会话查看/导出/批量删除、模型配置热更新、提示词模板编辑（存 sys_config + `_PROMPT_OVERRIDES` 缓存）。

## Setup / 开发命令

```bash
# 前端（本机 Windows，node 直调 vite，避免 npm .ps1 问题）
cd frontend/changjian-zhida
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit   # 类型检查
node node_modules/vite/bin/vite.js build            # 构建到 dist/

# 打包部署包（含 backend + dist + deploy，排除 chat.db/.env/.pyc）
python deploy_package.py

# 后端语法检查（本机 python 3.13 无 fastapi，只能 py_compile，不能 import 运行）
python -m py_compile backend/main.py
```

## 关键约束（务必遵守，否则踩坑）

1. **本机无法跑后端**：`backend/wheels/` 是 aarch64+py39 的 wheel，本机 Python 3.13 装不上。后端改动只能 `py_compile` 做语法检查，联调在服务器做。
2. **服务器环境**：openEuler 22.03 aarch64、Python 3.9.9、无公网、无 nginx。
3. **数据安全**：所有数据在 `backend/chat.db`。**重新部署严禁 `rm -rf`**，用 `unzip -o` 覆盖（部署包已排除 chat.db/.env）。
4. **版本锁定勿动**（aarch64+py39 兼容性）：numpy 1.24.4、onnxruntime 1.15.1、tokenizers 0.13.3、protobuf 3.20.3、opencv-headless 4.9.0.80、shapely 2.0.5、PyMuPDF 1.26.0。升级会破坏离线部署。
5. **Qwen 思考模式必须关**：请求带 `chat_template_kwargs={"enable_thinking": false}`，否则输出英文思考过程。
6. **前端无 markdown 渲染**：MessageList 用 `white-space: pre-wrap` 纯文本渲染，system prompt 里 `OUTPUT_FORMAT_NOTICE` 约束模型输出纯文本，别去掉。
7. **jieba 是 vendor 内嵌源码**（`sys.path` 注入），不 pip 安装、不写 requirements。
8. **BM25 用 `jieba.lcut_for_search`**（不是 `lcut`）。
9. **OCR 依赖安装必须 `--no-deps`**：rapidocr 声明依赖 `opencv-python`，本项目用 `opencv-python-headless` 替代（不同包名，pip 无法自动替代），不加 `--no-deps` 会报 "from versions: none"。

## 质量门槛（改完代码必须做）

- 前端改动：跑 `vue-tsc --noEmit` + `vite build`，确认产物进 `dist/`。
- 后端改动：跑 `python -m py_compile backend/main.py`。
- 需要部署时：跑 `python deploy_package.py` 重新打包 `changjian-zhida-deploy.zip`。
- 新增 Python 依赖：只允许纯 Python 源码内嵌 vendor，或跨平台下载 aarch64+py39 wheel（阿里云镜像 `--platform manylinux_2_17_aarch64 --python-version 39`）。

## 禁止事项

- 不要删除 `.workbuddy/` 目录（项目数据，非缓存）。
- 不要提交 `.env`、`chat.db`、wheels、模型文件、安装包到 git。
- 不要改依赖版本号（见「版本锁定勿动」）。
