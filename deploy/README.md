# 昌检智答AI助手 — 离线部署说明

面向检察机关的 AI Agent 智能问答平台。前端 Vue 3 + 后端 FastAPI + 模型推理 vLLM。

本方案为**离线部署**：服务器无需连接公网、无需安装 Nginx，后端 FastAPI 直接托管前端并转发 vLLM。

## 一、整体架构

```
浏览器 ──> FastAPI (80端口) ──┬─ /          前端静态文件 (dist)
                              ├─ /api/*     后端接口（对话、历史）
                              └─ 转发 ──> vLLM (143.9.233.5:8000)
                                            └─> SQLite (chat.db) 对话历史
```

| 组件 | 说明 | 地址/端口 |
|------|------|-----------|
| vLLM | 模型推理，Qwen3.6-35B-A3B（8-bit 量化） | 143.9.233.5:8000（已就绪） |
| FastAPI 后端 | 托管前端 + 流式转发 + 历史持久化 | 0.0.0.0:80 |
| SQLite | 对话历史存储 | backend/chat.db |

## 二、目录结构

```
changjian-zhida/
├── backend/                    # FastAPI 后端
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── vendor/                 # 内置依赖：jieba 分词源码 + bge 中文 embedding 模型（ONNX，跨架构）
│   └── wheels/                 # 离线依赖包（aarch64 / Python 3.9，含 onnxruntime/numpy/tokenizers）
├── dist/                       # 前端构建产物（已打包）
└── deploy/
    ├── install.sh              # 一键离线部署脚本
    └── README.md
```

## 三、部署步骤（服务器上，root 执行）

### 1. 上传并解压

用 MobaXterm 把 `changjian-zhida-deploy.zip` 拖到服务器，例如 `/opt/`：

```bash
cd /opt
unzip changjian-zhida-deploy.zip   # 解压出 changjian-zhida/
```

### 2. 一键部署

```bash
cd /opt/changjian-zhida
bash deploy/install.sh
```

脚本自动完成：
1. 检查 Python 3.9+（服务器已有）
2. 用 `wheels/` 里的包**离线安装**依赖（`pip install --no-index --find-links`）
3. 生成 `backend/.env`（vLLM 地址、模型名、静态目录、80 端口）
4. 注册并启动 systemd 服务 `changjian-zhida`
5. 健康检查

### 3. 访问

部署完成后浏览器打开 `http://<服务器IP>/` 即可使用。

> 若防火墙拦截，放行 80 端口：
> ```bash
> firewall-cmd --add-port=80/tcp --permanent && firewall-cmd --reload
> ```

## 四、环境变量说明（backend/.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| VLLM_BASE_URL | http://143.9.233.5:8000/v1 | vLLM OpenAI 兼容接口 |
| VLLM_MODEL | Qwen3.6_35B_A3B | vLLM 实际加载的模型名 |
| DB_PATH | ./chat.db | SQLite 数据库路径 |
| STATIC_DIR | ../dist | 前端构建产物目录 |
| HOST / PORT | 0.0.0.0 / 80 | 后端监听地址与端口 |
| TEMPERATURE | 0.7 | 生成温度 |
| MAX_TOKENS | 2048 | 单次回复最大 token |
| ENABLE_THINKING | false | Qwen3 思考模式开关 |
| MAX_UPLOAD_BYTES | 20 | 上传文档大小上限（MB） |
| MAX_UPLOAD_CHARS | 20000 | 单文档提取字符上限 |
| KB_CHUNK_SIZE | 500 | 知识库单块字符数 |
| KB_CHUNK_OVERLAP | 50 | 知识库块间重叠字符数 |
| KB_TOP_K | 5 | 知识库检索返回块数 |
| KB_MAX_DOC_CHARS | 200000 | 单文档入库字符上限 |
| KB_EMBED_ENABLED | true | 是否启用向量检索（false 则退化为纯 BM25） |
| KB_EMBED_MODEL_DIR | backend/vendor/bge | embedding 模型目录（默认自动定位） |
| KB_EMBED_BATCH | 64 | embedding 批大小 |
| KB_RRF_K | 60 | RRF 融合常数 |
| KB_RRF_CANDIDATES | 20 | 每条检索轨的候选数量 |

改完配置重启：`systemctl restart changjian-zhida`

## 五、功能说明

### 一期（对话核心）

1. **文档对话**：输入框左侧「回形针」按钮上传文档（支持 txt/md/csv/json/pdf/docx/xlsx/doc/wps），后端提取文本后随问题一起发给模型。
2. **终止对话**：生成中「发送」按钮会变成「停止」，点击立即中断当前回答，可马上开始新对话。
3. **用户隔离**：前端在浏览器 localStorage 生成唯一用户标识，随请求携带；每个浏览器只能看到自己的对话历史（同一浏览器视为同一用户）。
4. **多会话并发**：支持多个会话同时问答、多人同时使用，互不阻塞；后端 SQLite 已启用 WAL 模式支持并发读写。

### 二期（智能体 / 知识库 / OCR / 系统管理）

5. **智能体**：内置 6 个检察智能体（法条检索、案件分析、文书起草、类案参考、证据梳理、程序指引），对话时注入对应 system prompt。
6. **知识库（按部门分库 + 混合检索）**：默认 12 个部门知识库（第一~第八检察部、法律政策研究室、检务督察部、政治部、办公室、数字办），支持新建/删除库、库内上传/删除文档、点击查看原文。检索采用**混合检索**：BM25 关键词 + 向量语义（BGE-small-zh 中文 embedding 模型，ONNX 离线推理），RRF 倒数排名融合——既能精确匹配法条/罪名，又能语义泛化（如「偷东西」能命中「盗窃」条文）。若未部署 embedding 模型或 wheel，自动退化为纯 BM25 关键词检索。
7. **基于知识库的 RAG 问答**：在 AI 助手首页输入框选择知识库后提问，自动检索该库相关片段拼入 prompt；不选择则为普通对话。
8. **OCR 应用**：图片文字识别，引擎可插拔（tesseract → rapidocr_onnxruntime → paddleocr 自动探测）；未安装引擎时返回 503 提示（需离线单独安装对应 wheel）。
9. **系统管理**：统计概览（用户/会话/消息/近7天活跃）、会话列表、模型参数（temperature/max_tokens）热更新。

> 注意：当前模型为纯文本模型，不支持图片上传（图片识别走 OCR 模块）。
> doc/wps 老格式解析说明：后端内置了零依赖的启发式提取（能提取大部分正文）；若需要更高精度，建议在服务器安装 LibreOffice（`dnf install libreoffice-headless`，或内网源安装），后端会自动优先用 LibreOffice 转换。

## 六、验证

```bash
# 健康检查
curl http://127.0.0.1:80/api/health

# 流式对话测试
curl -N http://127.0.0.1:80/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 历史列表
curl http://127.0.0.1:80/api/conversations
```

## 七、运维

```bash
systemctl status changjian-zhida      # 查看状态
journalctl -u changjian-zhida -f      # 实时日志
systemctl restart changjian-zhida     # 重启
```

## 八、注意事项

1. **模型名**：`VLLM_MODEL` 填 `Qwen3.6_35B_A3B`（已按 `/v1/models` 确认，勿改）。
2. **思考模式**：Qwen3 默认输出思考过程，后端已用 `chat_template_kwargs.enable_thinking=false` 关闭，直接输出回答。
3. **端口冲突**：若 80 被占用，改 `.env` 的 `PORT` 并同步改 `/etc/systemd/system/changjian-zhida.service` 里的 `--port`，再重启。
4. **安全**：vLLM 的 8000 端口只应在内网开放，前端通过后端转发访问，不要暴露公网。
5. **数据库**：`chat.db` 建议定期备份。
6. **离线依赖**：`wheels/` 是针对 aarch64 + Python 3.9 下载的，若换架构或 Python 版本需重新下载。
7. **向量检索模型**：`vendor/bge/` 内嵌 BGE-small-zh-v1.5 模型（约 50MB，INT8 量化）；embedding 模型首次调用时懒加载（首次检索/上传会有数秒加载延迟，之后常驻内存）；模型加载失败时知识库自动退化为纯 BM25，不影响其他功能。
