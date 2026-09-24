"""
昌检智答AI助手 — 后端服务

职责：
1. 接收前端对话请求，流式转发给 vLLM（OpenAI 兼容接口）
2. 会话与消息持久化（SQLite），按用户隔离
3. 文件上传与文档文本解析（txt/md/pdf/docx 等）
4. 可选：托管前端构建产物（静态文件）

运行：
    uvicorn main:app --host 0.0.0.0 --port 80
"""

import os
import io
import json
import re
import math
import datetime
import sqlite3
import uuid
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import AsyncIterator, Optional, List

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 检护营商智能体 —— 食品安全行政处罚监督线索筛查（规则引擎模块，与 main.py 同目录）
import agent_yingshang

# 内置 vendor 依赖：纯 Python 源码包（如 jieba）随部署分发，运行时注入路径，无需 pip 安装
import sys as _sys

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
if _VENDOR_DIR.is_dir():
    _sys.path.insert(0, str(_VENDOR_DIR))

# 加载 .env 配置（若文件存在；系统环境变量优先级更高）
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 配置（环境变量优先，带默认值）
# ---------------------------------------------------------------------------
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://143.9.233.5:8000/v1").rstrip("/")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen3.6_35B_A3B")
DB_PATH = os.getenv("DB_PATH", "./chat.db")
STATIC_DIR = os.getenv("STATIC_DIR", "").strip()
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "false").lower() in ("1", "true", "yes")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "20")) * 1024 * 1024  # 默认 20MB
MAX_UPLOAD_CHARS = int(os.getenv("MAX_UPLOAD_CHARS", "20000"))  # 单文档提取字符上限

# 知识库（RAG）相关
KB_CHUNK_SIZE = int(os.getenv("KB_CHUNK_SIZE", "500"))       # 单块字符数
KB_CHUNK_OVERLAP = int(os.getenv("KB_CHUNK_OVERLAP", "50"))  # 块间重叠字符数
KB_TOP_K = int(os.getenv("KB_TOP_K", "5"))                   # 检索返回块数
KB_MAX_DOC_CHARS = int(os.getenv("KB_MAX_DOC_CHARS", "200000"))  # 单文档入库字符上限

# 向量检索（真实 RAG）：BGE 中文 embedding 模型（ONNX 格式），离线内嵌于 backend/vendor/bge/
# onnxruntime / numpy / tokenizers 为惰性导入，缺失时自动退化为纯 BM25 关键词检索
KB_EMBED_ENABLED = os.getenv("KB_EMBED_ENABLED", "true").lower() in ("1", "true", "yes")  # 是否启用向量检索
KB_EMBED_MODEL_DIR = os.getenv("KB_EMBED_MODEL_DIR", str(Path(__file__).resolve().parent / "vendor" / "bge"))  # 模型目录
KB_EMBED_BATCH = int(os.getenv("KB_EMBED_BATCH", "64"))          # embedding 批大小
KB_RRF_K = int(os.getenv("KB_RRF_K", "60"))                      # RRF 融合常数（越大越偏向靠前排名）
KB_RRF_CANDIDATES = int(os.getenv("KB_RRF_CANDIDATES", "20"))    # 每条轨的候选数量

# OCR（可插拔引擎）：默认 RapidOCR（onnxruntime 后端）
# rapidocr_onnxruntime 包内置 PP-OCRv4 模型（det/cls/rec），离线开箱即用；
# 若在 vendor/rapidocr/ 放置自定义 .onnx 模型，会优先使用本地模型
OCR_MODEL_DIR = os.getenv("OCR_MODEL_DIR", str(Path(__file__).resolve().parent / "vendor" / "rapidocr"))

# 默认部门知识库（所有用户共享，首次启动时自动创建）
DEFAULT_LIBRARIES = [
    "第一检察部",
    "第二检察部",
    "第三检察部",
    "第四检察部",
    "第五检察部",
    "第六检察部",
    "第七检察部",
    "第八检察部（法律政策研究室）",
    "检务督察部",
    "政治部",
    "办公室",
    "数字办",
]

# 知识库全局共享：所有知识库操作统一归属到这个固定用户标识（不再按用户隔离）
KB_USER = "shared"

# 删除知识库所需的管理员密码（可用环境变量 ADMIN_PASSWORD 覆盖）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@9000")

# ---------------------------------------------------------------------------
# 智能体定义：每个智能体一个专属 system prompt，注入对话首条消息
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM = (
    "你是「昌检智答」AI助手，服务于检察机关办案人员。"
    "你精通中国刑事、民事、行政及公益诉讼领域的法律法规、司法解释和检察实务。"
    "回答应专业、准确、条理清晰，引用法条时注明名称与条款；"
    "涉及具体案件时提示以在案证据和办案规范为准。"
)

# 身份说明：统一追加到所有对话（含智能体），避免模型被问身份时幻觉成其他厂商模型
IDENTITY_NOTICE = (
    "【身份说明】你是「昌检智答」平台的智能助手，由昌检智答平台部署，"
    "底层基于 Qwen（通义千问）大语言模型，服务于检察机关办案人员。"
    "当用户问及你的身份、名称、或所基于的模型时，请简洁、如实回答上述信息即可，"
    "不要展开详细的功能清单、业务领域介绍或免责声明等长篇内容；"
    "也不要声称自己是讯飞星火、文心一言、豆包或其他任何厂商的模型。"
)

# 输出格式约束：Qwen 倾向输出 Markdown 符号（### 标题、** 加粗、*** 分隔线），
# 前端为纯文本展示，故明确要求模型输出纯文本，避免符号原样出现在界面上
OUTPUT_FORMAT_NOTICE = (
    "【输出格式】请使用纯文本作答，不要使用任何 Markdown 标记符号，"
    "不要输出「#」「##」「###」「**」「***」「*」等标题、加粗、斜体或分隔线符号；"
    "需要分点或列项时，直接用「1.」「2.」「3.」或「第一，」「第二，」这类文字编号。"
)

# 智能体模块：预置智能体已移除，待重新设计（对话统一走默认助手）


# 提示词模板覆盖（后台可编辑，存 sys_config；为空则用代码里的默认常量）
_PROMPT_OVERRIDES: dict = {}


def _load_prompt_overrides() -> None:
    """启动时从 sys_config 加载可编辑的提示词模板到内存缓存。"""
    global _PROMPT_OVERRIDES
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT key, value FROM sys_config WHERE key IN (?, ?, ?)",
                ("system_prompt_default", "identity_notice", "output_format_notice"),
            ).fetchall()
        _PROMPT_OVERRIDES = {r["key"]: r["value"] for r in rows}
    except Exception:
        _PROMPT_OVERRIDES = {}


def system_prompt_for() -> str:
    base = _PROMPT_OVERRIDES.get("system_prompt_default") or DEFAULT_SYSTEM
    identity = _PROMPT_OVERRIDES.get("identity_notice") or IDENTITY_NOTICE
    fmt = _PROMPT_OVERRIDES.get("output_format_notice") or OUTPUT_FORMAT_NOTICE
    return base + "\n\n" + identity + "\n\n" + fmt


app = FastAPI(title="昌检智答AI助手后端")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# SQLite 持久化
# ---------------------------------------------------------------------------
def _db() -> sqlite3.Connection:
    # timeout 让并发写等待锁，避免 "database is locked"
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        # WAL 模式：读写并发，适合多人同时问答
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL DEFAULT 'default',
                title       TEXT NOT NULL,
                create_time INTEGER NOT NULL,
                update_time INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                attachments     TEXT,
                create_time     INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id)"
        )
        # 兼容旧库迁移：补 user_id / attachments 列
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversations)")]
        if "user_id" not in cols:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
            )
        mcols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
        if "attachments" not in mcols:
            conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        # 知识库（部门库）表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_libraries (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL DEFAULT 'default',
                name        TEXT NOT NULL,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                create_time INTEGER NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kblib_user ON kb_libraries(user_id)")
        # 兼容旧库迁移：补 sort_order 列
        kcols = [r[1] for r in conn.execute("PRAGMA table_info(kb_libraries)")]
        if "sort_order" not in kcols:
            conn.execute(
                "ALTER TABLE kb_libraries ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
            )
        # 知识库文档表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_documents (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL DEFAULT 'default',
                library_id  TEXT NOT NULL DEFAULT '',
                filename    TEXT NOT NULL,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                char_count  INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL,
                create_time INTEGER NOT NULL
            )
            """
        )
        # 兼容旧库迁移：补 library_id 列
        kdcols = [r[1] for r in conn.execute("PRAGMA table_info(kb_documents)")]
        if "library_id" not in kdcols:
            conn.execute(
                "ALTER TABLE kb_documents ADD COLUMN library_id TEXT NOT NULL DEFAULT ''"
            )
        # 知识库分块表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id        TEXT PRIMARY KEY,
                doc_id    TEXT NOT NULL,
                idx       INTEGER NOT NULL,
                content   TEXT NOT NULL,
                vec       BLOB
            )
            """
        )
        # 兼容旧库迁移：补 vec 列（向量检索的 embedding 结果，BLOB 存 float32 数组）
        kc_cols = [r[1] for r in conn.execute("PRAGMA table_info(kb_chunks)")]
        if "vec" not in kc_cols:
            conn.execute("ALTER TABLE kb_chunks ADD COLUMN vec BLOB")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kbchunk_doc ON kb_chunks(doc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kbdoc_user ON kb_documents(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kbdoc_lib ON kb_documents(library_id)")
        # 系统配置表（模型参数等运行时配置）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sys_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # 回答质量反馈表（点赞/点踩）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id              TEXT PRIMARY KEY,
                message_id      TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                rating          INTEGER NOT NULL,
                create_time     INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fb_conv ON feedback(conversation_id)"
        )

    # 检护营商智能体：主体碰撞表（市监局许可/备案数据，按统一社会信用代码索引）
    with _db() as conn:
        conn.executescript(agent_yingshang.COLLISION_TABLE_SQL)

    # 加载提示词模板覆盖（后台可编辑，存 sys_config）
    _load_prompt_overrides()


def _now_ms() -> int:
    return int(time.time() * 1000)


def get_user_id(x_user_id: Optional[str]) -> str:
    return (x_user_id or "").strip() or "default"


def ensure_conversation(conv_id: str, user_id: str, title: str) -> None:
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO conversations(id, user_id, title, create_time, update_time) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, user_id, title, _now_ms(), _now_ms()),
            )
        else:
            conn.execute(
                "UPDATE conversations SET update_time = ? WHERE id = ?",
                (_now_ms(), conv_id),
            )


def save_message(conv_id: str, role: str, content: str, attachments: Optional[list] = None) -> dict:
    msg_id = uuid.uuid4().hex
    ts = _now_ms()
    attach_json = json.dumps(attachments, ensure_ascii=False) if attachments else None
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages(id, conversation_id, role, content, attachments, create_time) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, conv_id, role, content, attach_json, ts),
        )
        conn.execute(
            "UPDATE conversations SET update_time = ? WHERE id = ?", (ts, conv_id)
        )
    return {"id": msg_id, "role": role, "content": content, "createTime": ts}


def get_conversation_messages(conv_id: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, role, content, attachments, create_time FROM messages "
            "WHERE conversation_id = ? ORDER BY create_time ASC",
            (conv_id,),
        ).fetchall()
    out = []
    for r in rows:
        msg = {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "createTime": r["create_time"],
        }
        if r["attachments"]:
            try:
                msg["attachments"] = json.loads(r["attachments"])
            except json.JSONDecodeError:
                pass
        out.append(msg)
    return out


def list_conversations(user_id: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, title, create_time, update_time FROM conversations "
            "WHERE user_id = ? ORDER BY update_time DESC",
            (user_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "createTime": r["create_time"],
            "updateTime": r["update_time"],
        }
        for r in rows
    ]


def get_conversation_row(conv_id: str, user_id: str):
    with _db() as conn:
        return conn.execute(
            "SELECT id, title, create_time, update_time FROM conversations "
            "WHERE id = ? AND user_id = ?",
            (conv_id, user_id),
        ).fetchone()


def conversation_owner(conv_id: str) -> Optional[str]:
    """返回会话归属的用户 id；不存在则返回 None。"""
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    return row["user_id"] if row else None


def delete_conversation(conv_id: str, user_id: str) -> bool:
    with _db() as conn:
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conv_id,)
        )
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id)
        )
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# 文档文本提取
# ---------------------------------------------------------------------------
TEXT_EXTS = {
    "txt", "md", "markdown", "csv", "tsv", "log", "json", "text",
    "html", "htm", "xml", "yaml", "yml", "ini", "conf", "cfg",
    "py", "js", "ts", "jsx", "tsx", "java", "c", "cpp", "h", "sh", "sql",
}


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="ignore")


def _detect_type(data: bytes) -> str:
    """根据文件头判断真实类型（而非扩展名）。"""
    if data[:4] == b"PK\x03\x04":
        return "zip"  # docx/xlsx 等 OOXML 格式（含伪装成 .wps 的 docx）
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "ole"  # doc/wps/xls 老式 OLE 格式
    if data[:4] == b"%PDF":
        return "pdf"
    return "unknown"


def _soffice_convert(data: bytes, ext: str) -> str:
    """用 LibreOffice headless 转纯文本（最可靠，需服务器已装 soffice/libreoffice）。"""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, f"input.{ext or 'doc'}")
        with open(src, "wb") as f:
            f.write(data)
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, src],
                timeout=60,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            out = os.path.join(tmp, "input.txt")
            if os.path.exists(out):
                with open(out, "rb") as f:
                    return f.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            pass
    return ""


def _extract_ole_text(data: bytes) -> str:
    """从 OLE 复合文档（.doc/.wps/.xls 老格式）启发式提取文本（零系统依赖，效果略粗糙）。"""
    try:
        import olefile
        import re
    except ImportError:
        return ""
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
        streams: list[bytes] = []
        for entry in ole.listdir():
            try:
                streams.append(ole.openstream(entry).read())
            except Exception:  # noqa: BLE001
                continue
        ole.close()
    except Exception:  # noqa: BLE001
        return ""

    best = ""
    for raw in streams:
        try:
            s = raw.decode("utf-16-le", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        # 提取连续可读片段（中文、英文、数字、常见标点）
        parts = re.findall(
            r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffefA-Za-z0-9，。、；：！？（）【】《》·\u2014\u2015\u2018\u2019\u201c\u201d\u2026\r\n\t ]{4,}",
            s,
        )
        if parts:
            candidate = "\n".join(p.strip() for p in parts if p.strip())
            if len(candidate) > len(best):
                best = candidate
    return best


def extract_text(filename: str, data: bytes) -> str:
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    ftype = _detect_type(data)

    try:
        # 纯文本（且不是 OLE 二进制）
        if ext in TEXT_EXTS and ftype != "ole":
            return _decode_text(data)

        # zip 格式：docx / xlsx（含伪装成 .wps 的 docx）
        if ftype == "zip":
            text = ""
            try:
                import docx

                d = docx.Document(io.BytesIO(data))
                text = "\n".join(p.text for p in d.paragraphs)
            except Exception:  # noqa: BLE001
                text = ""
            if text.strip():
                return text
            try:
                import openpyxl

                wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                lines: list[str] = []
                for ws in wb.worksheets:
                    lines.append(f"【工作表：{ws.title}】")
                    for row in ws.iter_rows(values_only=True):
                        cells = [str(c) for c in row if c is not None and str(c).strip()]
                        if cells:
                            lines.append("\t".join(cells))
                text = "\n".join(lines)
            except Exception:  # noqa: BLE001
                text = ""
            return text

        # PDF
        if ftype == "pdf" or ext == "pdf":
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(data))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)

        # OLE 老格式（doc/wps/xls）：优先 LibreOffice，兜底 olefile 启发式
        if ftype == "ole":
            text = _soffice_convert(data, ext)
            if text.strip():
                return text
            return _extract_ole_text(data)
    except Exception:  # noqa: BLE001
        return ""

    # 兜底：按文本读取
    return _decode_text(data)


# ---------------------------------------------------------------------------
# 知识库（RAG）：jieba 分词 + BM25 关键词检索
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> List[str]:
    """中文分词：优先 jieba 搜索引擎模式（保留完整词+子词，提升召回），不可用时退化。"""
    try:
        import jieba

        toks = [t.strip() for t in jieba.lcut_for_search(text) if t.strip()]
        if toks:
            return toks
    except Exception:  # noqa: BLE001
        pass
    return re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", text.lower())


# 法律条文编号：如「第二百六十四条」「第264条」等
_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零\d]+条")


def _split_fixed(text: str) -> List[str]:
    """固定长度切块，块间带重叠（无结构时的兜底切法）。"""
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + KB_CHUNK_SIZE, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - KB_CHUNK_OVERLAP
    return chunks


def _split_chunks(text: str) -> List[str]:
    """结构感知切块。

    法律条文优先按「第X条」切分（每条独立成块，检索更精准）；条文超长再按固定长度切；
    无条文结构（案例、报告、内部规范等）退化为固定长度 + 重叠切块。
    """
    matches = list(_ARTICLE_RE.finditer(text))
    if len(matches) < 2:
        return _split_fixed(text)
    chunks: List[str] = []
    # 第一条文之前的内容（标题、目录、总则等）
    if matches[0].start() > 0:
        head = text[: matches[0].start()].strip()
        if head:
            chunks.extend(_split_fixed(head))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = text[start:end]
        if len(seg) > KB_CHUNK_SIZE:
            chunks.extend(_split_fixed(seg))
        else:
            chunks.append(seg)
    return [c for c in chunks if c.strip()]


class _BM25:
    """轻量 BM25 检索器（内存倒排，适合中小规模知识库）。"""

    def __init__(self, docs: List[str]):
        self.docs = docs
        self.N = len(docs)
        self.doc_freqs: dict = {}
        self.doc_lens: List[int] = []
        self.term_freqs: List[dict] = []
        for d in docs:
            toks = _tokenize(d)
            self.doc_lens.append(len(toks))
            tf: dict = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            self.term_freqs.append(tf)
            for t in set(toks):
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1
        self.avgdl = sum(self.doc_lens) / max(1, self.N)
        self.k1 = 1.5
        self.b = 0.75

    def _score(self, query: str, idx: int) -> float:
        tf = self.term_freqs[idx]
        dl = max(1, self.doc_lens[idx])
        s = 0.0
        for t in _tokenize(query):
            df = self.doc_freqs.get(t, 0)
            if df == 0:
                continue
            tfd = tf.get(t, 0)
            if tfd == 0:
                continue
            idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
            s += idf * (tfd * (self.k1 + 1)) / (
                tfd + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            )
        return s

    def search(self, query: str, top_k: int) -> List[tuple]:
        scored = [(i, self._score(query, i)) for i in range(self.N)]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


# ---------------------------------------------------------------------------
# 向量检索（真实 RAG）：BGE embedding 模型懒加载 + 向量化 + RRF 混合
# ---------------------------------------------------------------------------
_EMBED_LOADED = False
_EMBED_MODEL = None  # (tokenizer, session, numpy) 或 None


def _load_embedding_model():
    """懒加载 embedding 模型（onnxruntime + tokenizers + numpy），失败返回 None。

    三个依赖均为惰性导入：未安装 onnxruntime / 模型文件缺失时返回 None，
    调用方自动退化为纯 BM25 关键词检索，保证知识库功能始终可用。
    """
    global _EMBED_LOADED, _EMBED_MODEL
    if _EMBED_LOADED:
        return _EMBED_MODEL
    _EMBED_LOADED = True
    if not KB_EMBED_ENABLED:
        return None
    try:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = Path(KB_EMBED_MODEL_DIR)
        onnx_file = model_dir / "model_qint8.onnx"
        if not onnx_file.exists():
            onnx_file = model_dir / "model.onnx"
        if not onnx_file.exists():
            return None
        tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        tok.enable_truncation(max_length=512)
        sess = ort.InferenceSession(str(onnx_file))
        _EMBED_MODEL = (tok, sess, np)
    except Exception:
        _EMBED_MODEL = None
    return _EMBED_MODEL


def _embed_texts(texts: List[str]):
    """把文本列表向量化为 (n, 512) float32 ndarray（已 L2 归一化）。失败返回 None。"""
    m = _load_embedding_model()
    if m is None or not texts:
        return None
    tok, sess, np = m
    try:
        encs = tok.encode_batch(list(texts))
        max_len = max(len(e.ids) for e in encs)
        ids_arr = np.zeros((len(encs), max_len), dtype=np.int64)
        attn = np.zeros((len(encs), max_len), dtype=np.int64)
        ttype = np.zeros((len(encs), max_len), dtype=np.int64)
        for i, e in enumerate(encs):
            ids_arr[i, : len(e.ids)] = e.ids
            attn[i, : len(e.ids)] = 1
        out = sess.run(
            None,
            {"input_ids": ids_arr, "attention_mask": attn, "token_type_ids": ttype},
        )
        h = out[0]  # (n, seq, 512)
        cls = h[:, 0, :]  # 取 CLS 作为句向量
        norms = np.linalg.norm(cls, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (cls / norms).astype(np.float32)
    except Exception:
        return None


def _rrf_fusion(ranked_lists: List[List[tuple]], k: int) -> List[tuple]:
    """RRF 倒数排名融合：输入若干 [(idx, score)] 已降序列表，输出 [(idx, fused)] 降序。

    只关心「排名」而非原始分数，天然归一化，避免 BM25 分数与余弦相似度量纲不一致的问题。
    """
    fused: dict = {}
    for lst in ranked_lists:
        for rank, (idx, score) in enumerate(lst):
            if score <= 0:
                continue
            fused[idx] = fused.get(idx, 0) + 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])


def _ensure_default_libraries(user_id: str) -> None:
    """确保用户拥有 12 个默认部门知识库，并保证顺序按 DEFAULT_LIBRARIES 排列。"""
    with _db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM kb_libraries WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        if count == 0:
            for i, name in enumerate(DEFAULT_LIBRARIES):
                conn.execute(
                    "INSERT INTO kb_libraries(id, user_id, name, sort_order, create_time) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, user_id, name, i, _now_ms()),
                )
            return
        # 老数据迁移：sort_order 全为 0 时，按默认顺序回填；自建库排到末尾
        non_zero = conn.execute(
            "SELECT COUNT(*) FROM kb_libraries WHERE user_id = ? AND sort_order != 0",
            (user_id,),
        ).fetchone()[0]
        if non_zero == 0:
            name_to_idx = {name: i for i, name in enumerate(DEFAULT_LIBRARIES)}
            rows = conn.execute(
                "SELECT id, name FROM kb_libraries WHERE user_id = ? ORDER BY create_time ASC",
                (user_id,),
            ).fetchall()
            extra = len(DEFAULT_LIBRARIES)
            for r in rows:
                idx = name_to_idx.get(r["name"], extra)
                conn.execute(
                    "UPDATE kb_libraries SET sort_order = ? WHERE id = ?", (idx, r["id"])
                )


# 注意：知识库现已支持「公开(shared) / 私有(具体用户)」两种归属。
# 旧版「按用户隔离 → 全局共享」的一次性迁移已完成，这里不再做任何跨 user_id 合并，
# 否则会把新建的私有库误合并到 shared。


def _get_library_owner(lib_id: str) -> Optional[str]:
    """返回知识库的归属（'shared' 表示公开，其余为用户 id 表示私有），不存在返回 None。"""
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id FROM kb_libraries WHERE id = ?", (lib_id,)
        ).fetchone()
    return row["user_id"] if row else None


def _can_access_library(user_id: str, owner: Optional[str]) -> bool:
    """判断 user_id 是否可访问归属为 owner 的库（公开库所有人可访问，私有库仅本人）。"""
    return owner is not None and (owner == KB_USER or owner == user_id)


def _list_libraries(user_id: str) -> list[dict]:
    """列出用户可见的知识库：公开(shared)库 + 本人私有库，公开库排前。"""
    with _db() as conn:
        rows = conn.execute(
            "SELECT l.id, l.name, l.user_id, l.create_time, COUNT(d.id) AS doc_count "
            "FROM kb_libraries l LEFT JOIN kb_documents d ON d.library_id = l.id "
            "WHERE l.user_id = ? OR l.user_id = ? "
            "GROUP BY l.id "
            "ORDER BY (l.user_id != ?) ASC, l.sort_order ASC, l.create_time ASC",
            (KB_USER, user_id, KB_USER),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "docCount": r["doc_count"],
            "createTime": r["create_time"],
            "isPublic": r["user_id"] == KB_USER,
        }
        for r in rows
    ]


def _add_library(user_id: str, name: str, is_public: bool = True) -> dict:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="知识库名称不能为空")
    owner = KB_USER if is_public else user_id
    with _db() as conn:
        dup = conn.execute(
            "SELECT id FROM kb_libraries WHERE user_id = ? AND name = ?", (owner, name)
        ).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail="已存在同名知识库")
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM kb_libraries WHERE user_id = ?",
            (owner,),
        ).fetchone()[0]
        lib_id = uuid.uuid4().hex
        ts = _now_ms()
        conn.execute(
            "INSERT INTO kb_libraries(id, user_id, name, sort_order, create_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (lib_id, owner, name, max_order + 1, ts),
        )
    return {"id": lib_id, "name": name, "docCount": 0, "createTime": ts, "isPublic": is_public}


def _delete_library(user_id: str, lib_id: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM kb_libraries WHERE id = ? AND user_id = ?", (lib_id, user_id)
        )
        if cur.rowcount == 0:
            return False
        doc_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM kb_documents WHERE library_id = ?", (lib_id,)
            ).fetchall()
        ]
        conn.execute("DELETE FROM kb_documents WHERE library_id = ?", (lib_id,))
        for did in doc_ids:
            conn.execute("DELETE FROM kb_chunks WHERE doc_id = ?", (did,))
    return True


def _get_library_name(user_id: str, lib_id: str) -> str:
    """返回用户可见库的名称（公开库或本人私有库），不可见/不存在返回空串。"""
    with _db() as conn:
        row = conn.execute(
            "SELECT name FROM kb_libraries WHERE id = ? AND (user_id = ? OR user_id = ?)",
            (lib_id, user_id, KB_USER),
        ).fetchone()
    return row["name"] if row else ""


def _add_kb_document(user_id: str, library_id: str, filename: str, content: str) -> dict:
    doc_id = uuid.uuid4().hex
    ts = _now_ms()
    chunks = _split_chunks(content)
    # 向量化（若 embedding 可用）：分批 embed，失败则整体不存向量（检索时自动走纯 BM25）
    vecs: Optional[List[bytes]] = None
    if _load_embedding_model() is not None and chunks:
        vecs = []
        try:
            for i in range(0, len(chunks), KB_EMBED_BATCH):
                bv = _embed_texts(chunks[i : i + KB_EMBED_BATCH])
                if bv is None:
                    vecs = None
                    break
                vecs.extend(v.tobytes() for v in bv)
        except Exception:
            vecs = None
    with _db() as conn:
        conn.execute(
            "INSERT INTO kb_documents(id, user_id, library_id, filename, title, content, char_count, chunk_count, create_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, library_id, filename, filename, content, len(content), len(chunks), ts),
        )
        for i, c in enumerate(chunks):
            v = vecs[i] if vecs is not None else None
            conn.execute(
                "INSERT INTO kb_chunks(id, doc_id, idx, content, vec) VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, doc_id, i, c, v),
            )
    return {
        "id": doc_id,
        "filename": filename,
        "charCount": len(content),
        "chunkCount": len(chunks),
        "createTime": ts,
    }


def _list_kb_documents(user_id: str, library_id: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, filename, char_count, chunk_count, create_time FROM kb_documents "
            "WHERE user_id = ? AND library_id = ? ORDER BY create_time DESC",
            (user_id, library_id),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "charCount": r["char_count"],
            "chunkCount": r["chunk_count"],
            "createTime": r["create_time"],
        }
        for r in rows
    ]


def _get_kb_document(user_id: str, doc_id: str) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute(
            "SELECT id, library_id, filename, content, char_count, chunk_count, create_time "
            "FROM kb_documents WHERE id = ? AND (user_id = ? OR user_id = ?)",
            (doc_id, user_id, KB_USER),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "libraryId": row["library_id"],
        "filename": row["filename"],
        "content": row["content"],
        "charCount": row["char_count"],
        "chunkCount": row["chunk_count"],
        "createTime": row["create_time"],
    }


def _kb_search(
    user_id: str, query: str, top_k: int, library_id: Optional[str] = None
) -> List[dict]:
    """混合检索：BM25 关键词 + 向量语义，RRF 融合。向量不可用时退化为纯 BM25。"""
    if library_id:
        # 指定库：先校验用户可见，不可见返回空
        if not _get_library_name(user_id, library_id):
            return []
        sql = (
            "SELECT c.id, c.doc_id, c.content, c.vec, d.filename, l.name AS lib_name FROM kb_chunks c "
            "JOIN kb_documents d ON c.doc_id = d.id "
            "JOIN kb_libraries l ON d.library_id = l.id "
            "WHERE d.library_id = ?"
        )
        params = (library_id,)
    else:
        sql = (
            "SELECT c.id, c.doc_id, c.content, c.vec, d.filename, l.name AS lib_name FROM kb_chunks c "
            "JOIN kb_documents d ON c.doc_id = d.id "
            "LEFT JOIN kb_libraries l ON d.library_id = l.id "
            "WHERE d.user_id = ? OR d.user_id = ?"
        )
        params = (KB_USER, user_id)
    with _db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []

    contents = [r["content"] for r in rows]

    # 轨1：BM25 关键词
    bm = _BM25(contents)
    bm_hits = bm.search(query, KB_RRF_CANDIDATES)  # [(idx, score)] 降序

    # 轨2：向量语义（若 embedding 可用）
    vec_hits = None
    m = _load_embedding_model()
    if m is not None:
        np = m[2]
        qv = _embed_texts([query])
        if qv is not None:
            try:
                mats = []
                idxs = []
                for i, r in enumerate(rows):
                    if r["vec"] is not None:
                        v = np.frombuffer(r["vec"], dtype=np.float32)
                        if v.shape[0] == qv.shape[1]:
                            mats.append(v)
                            idxs.append(i)
                if mats:
                    M = np.stack(mats)  # (m, 512)
                    scores = (M @ qv[0]).astype(np.float64)
                    order = np.argsort(-scores)[:KB_RRF_CANDIDATES]
                    vec_hits = [(idxs[int(j)], float(scores[int(j)])) for j in order]
            except Exception:
                vec_hits = None

    # RRF 融合（向量轨不可用时退化为纯 BM25 排序）
    if vec_hits:
        ranked = _rrf_fusion([bm_hits, vec_hits], KB_RRF_K)
    else:
        ranked = bm_hits

    result: List[dict] = []
    for idx, sc in ranked:
        if sc <= 0:
            continue
        r = rows[idx]
        result.append(
            {
                "docId": r["doc_id"],
                "filename": r["filename"],
                "library": r["lib_name"],
                "content": r["content"],
                "score": round(sc, 4),
            }
        )
        if len(result) >= top_k:
            break
    return result


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class Attachment(BaseModel):
    filename: str
    content: str


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None  # 为空则由后端生成新会话
    message: str
    attachments: Optional[List[Attachment]] = None
    library_id: Optional[str] = None  # 选择知识库进行 RAG 问答（为空则普通对话）
    deep_think: Optional[bool] = None  # 深度思考：True 开启模型思考模式，None 用全局默认


class KBQuery(BaseModel):
    query: str
    top_k: Optional[int] = None  # 缺省用 KB_TOP_K
    library_id: Optional[str] = None  # 为空则检索全部库


class LibraryCreate(BaseModel):
    name: str
    is_public: Optional[bool] = True  # 是否公开（False=私有，仅创建者可见）


class AdminConfigRequest(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class FeedbackRequest(BaseModel):
    message_id: str
    conversation_id: str
    rating: int  # 1=好评 -1=差评


class PromptsRequest(BaseModel):
    system_prompt_default: Optional[str] = None
    identity_notice: Optional[str] = None
    output_format_notice: Optional[str] = None


class BatchDeleteRequest(BaseModel):
    ids: List[str]


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "model": VLLM_MODEL, "vllm": VLLM_BASE_URL}


@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    """提交回答质量反馈（点赞/点踩）。"""
    if req.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating 必须是 1 或 -1")
    with _db() as conn:
        conn.execute(
            "INSERT INTO feedback(id, message_id, conversation_id, rating, create_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, req.message_id, req.conversation_id, req.rating, _now_ms()),
        )
    return {"ok": True}


# 图片等模型无法理解的格式（当前模型为纯文本，无视觉能力）
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """上传文档，提取文本返回（不落盘）。"""
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext in IMAGE_EXTS:
        raise HTTPException(
            status_code=422,
            detail="当前模型不支持图片，请上传文档或将文字直接输入",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件过大")

    text = extract_text(filename, data)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="无法提取文档内容：请用 txt/md/pdf/docx/xlsx 格式；"
            "doc/wps 老格式建议在服务器安装 LibreOffice 以获得更好解析",
        )
    text = text[:MAX_UPLOAD_CHARS]
    return {
        "filename": filename or "未命名",
        "content": text,
        "chars": len(text),
    }


# ---------------------------------------------------------------------------
# vLLM 流式转发辅助（对话 / 知识库问答 / 智能体共用）
# ---------------------------------------------------------------------------
async def _vllm_deltas(messages: list, enable_thinking: bool = False) -> AsyncIterator[dict]:
    """向 vLLM 发起流式请求，逐段 yield 结构化片段：{"reasoning": ...} 或 {"delta": ...}；异常直接抛出。"""
    payload = {
        "model": VLLM_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
    ) as client:
        async with client.stream(
            "POST", f"{VLLM_BASE_URL}/chat/completions", json=payload
        ) as resp:
            # 非 200：先读 body 拿到 vLLM 的具体错误原因（流式模式下 raise_for_status 拿不到 body）
            if resp.status_code != 200:
                try:
                    body = (await resp.aread()).decode("utf-8", errors="ignore")
                except Exception:  # noqa: BLE001
                    body = ""
                raise RuntimeError(f"模型服务返回错误 {resp.status_code}：{body[:500]}")
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0].get("delta", {})
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    content = delta.get("content")
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if reasoning:
                    yield {"reasoning": reasoning}
                if content:
                    yield {"delta": content}


def _error_to_sse(e: Exception) -> str:
    """把异常转成 SSE error 事件字符串。"""
    if isinstance(e, httpx.HTTPStatusError):
        detail = ""
        try:
            detail = (e.response.text or "")[:300]
        except Exception:  # noqa: BLE001
            pass
        err = f"模型服务返回错误 {e.response.status_code}：{detail}".strip()
    elif isinstance(e, httpx.HTTPError):
        err = f"无法连接模型服务：{e}"
    else:
        msg = str(e) or "调用模型失败"
        # RuntimeError 已自带完整错误信息（如"模型服务返回错误 400：..."），不再加冗余前缀
        err = msg if "模型服务返回错误" in msg else f"调用模型失败：{msg}"
    return f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n"


@app.post("/api/chat/completions")
async def chat_completions(req: ChatRequest, x_user_id: Optional[str] = Header(default=None)):
    """流式对话：转发 vLLM，返回 SSE；同时持久化消息（按用户隔离）。"""
    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

    user_id = get_user_id(x_user_id)
    title = text[:20].strip() or "新对话"
    attachments = req.attachments or []

    # 越权校验：会话已存在但归属他人时拒绝
    if req.conversation_id:
        owner = conversation_owner(req.conversation_id)
        if owner is not None and owner != user_id:
            raise HTTPException(status_code=403, detail="无权访问该会话")
    conv_id = req.conversation_id or uuid.uuid4().hex

    # 1. 确保会话存在，保存用户消息（含附件元数据）
    ensure_conversation(conv_id, user_id, title)
    save_message(
        conv_id,
        "user",
        text,
        [{"filename": a.filename, "content": a.content} for a in attachments] or None,
    )

    # 2. 读取历史，拼 OpenAI messages（附件文本拼入 user 内容）
    history = get_conversation_messages(conv_id)
    messages: list[dict] = []
    # 智能体专属 system prompt 放在最前
    sys_content = system_prompt_for()
    retrieval_hits: list = []  # RAG 召回片段（回传给前端展示引用来源）
    # 选择知识库时：检索片段拼入同一个 system（仅本次请求，不写入历史）
    # 注意：不能追加第二个 system 消息，Qwen chat template 对连续 system 会返回 400
    if req.library_id:
        if not _get_library_name(user_id, req.library_id):
            raise HTTPException(status_code=403, detail="无权访问该知识库")
        hits = _kb_search(user_id, text, KB_TOP_K, req.library_id)
        lib_name = _get_library_name(user_id, req.library_id)
        if hits:
            retrieval_hits = [
                {"docId": h["docId"], "filename": h["filename"], "content": h["content"], "score": h["score"]}
                for h in hits
            ]
            ctx = "\n\n".join(
                f"【片段{i + 1} · 来源：{h['filename']}】\n{h['content']}"
                for i, h in enumerate(hits)
            )
            sys_content += (
                f"\n\n以下是知识库「{lib_name}」中检索到的相关内容，请优先依据这些内容回答用户问题，"
                f"不要编造片段之外的内容；若不足以回答请明确说明：\n\n{ctx}"
            )
        else:
            sys_content += (
                f"\n\n用户从知识库「{lib_name}」发起提问，但该库中未检索到相关内容，"
                f"请说明该知识库暂无相关资料。"
            )
    messages.append({"role": "system", "content": sys_content})
    for m in history:
        if m["role"] == "user" and m.get("attachments"):
            attach_text = "\n\n".join(
                f"【附件：{a['filename']}】\n{a['content']}" for a in m["attachments"]
            )
            messages.append({"role": "user", "content": f"{attach_text}\n\n{m['content']}"})
        else:
            messages.append({"role": m["role"], "content": m["content"]})

    # 深度思考：请求级覆盖全局开关
    enable_thinking = req.deep_think if req.deep_think is not None else ENABLE_THINKING

    async def generate() -> AsyncIterator[str]:
        full = ""
        try:
            # RAG 召回片段先发给前端（用于展示引用来源）
            if retrieval_hits:
                yield f"data: {json.dumps({'retrieval': retrieval_hits}, ensure_ascii=False)}\n\n"
            async for chunk in _vllm_deltas(messages, enable_thinking):
                if "reasoning" in chunk:
                    yield f"data: {json.dumps({'reasoning': chunk['reasoning']}, ensure_ascii=False)}\n\n"
                elif "delta" in chunk:
                    full += chunk["delta"]
                    yield f"data: {json.dumps({'delta': chunk['delta']}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield _error_to_sse(e)
        finally:
            if full:
                save_message(conv_id, "assistant", full)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv_id,
        },
    )


@app.get("/api/conversations")
def get_conversations(x_user_id: Optional[str] = Header(default=None)):
    return {"data": list_conversations(get_user_id(x_user_id))}


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str, x_user_id: Optional[str] = Header(default=None)):
    row = get_conversation_row(conv_id, get_user_id(x_user_id))
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": row["id"],
        "title": row["title"],
        "createTime": row["create_time"],
        "updateTime": row["update_time"],
        "messages": get_conversation_messages(conv_id),
    }


@app.delete("/api/conversations/{conv_id}")
def remove_conversation(conv_id: str, x_user_id: Optional[str] = Header(default=None)):
    if not delete_conversation(conv_id, get_user_id(x_user_id)):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 知识库（部门库）接口
# ---------------------------------------------------------------------------
@app.get("/api/kb/libraries")
def kb_list_libraries(x_user_id: Optional[str] = Header(default=None)):
    """列出知识库：公开(shared)库 + 本人私有库；首次自动创建 12 个默认部门库。"""
    _ensure_default_libraries(KB_USER)
    return {"data": _list_libraries(get_user_id(x_user_id))}


@app.post("/api/kb/libraries")
def kb_create_library(req: LibraryCreate, x_user_id: Optional[str] = Header(default=None)):
    return _add_library(get_user_id(x_user_id), req.name, req.is_public)


@app.delete("/api/kb/libraries/{lib_id}")
def kb_delete_library(
    lib_id: str,
    x_user_id: Optional[str] = Header(default=None),
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """删除知识库：公开库需管理员密码；私有库仅创建者可删（无需密码）。"""
    uid = get_user_id(x_user_id)
    owner = _get_library_owner(lib_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if owner == KB_USER:
        if x_admin_password != ADMIN_PASSWORD:
            raise HTTPException(status_code=403, detail="管理员密码错误")
    elif owner != uid:
        raise HTTPException(status_code=403, detail="无权删除该知识库")
    if not _delete_library(owner, lib_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"ok": True}


@app.post("/api/kb/libraries/{lib_id}/documents")
async def kb_upload_document(
    lib_id: str,
    file: UploadFile = File(...),
    x_user_id: Optional[str] = Header(default=None),
):
    """上传文档到指定知识库（提取文本 + 切块 + 建索引）。"""
    uid = get_user_id(x_user_id)
    owner = _get_library_owner(lib_id)
    if not _can_access_library(uid, owner):
        raise HTTPException(status_code=404, detail="知识库不存在")
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in IMAGE_EXTS:
        raise HTTPException(status_code=422, detail="知识库暂不支持图片，请上传文档格式")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件过大")
    text = extract_text(filename, data)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="无法提取文档内容，请使用 txt/md/pdf/docx/xlsx/doc 等格式",
        )
    text = text[:KB_MAX_DOC_CHARS]
    return _add_kb_document(owner, lib_id, filename or "未命名", text)


@app.get("/api/kb/libraries/{lib_id}/documents")
def kb_list_documents(lib_id: str, x_user_id: Optional[str] = Header(default=None)):
    uid = get_user_id(x_user_id)
    owner = _get_library_owner(lib_id)
    if not _can_access_library(uid, owner):
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"data": _list_kb_documents(owner, lib_id)}


@app.delete("/api/kb/documents/{doc_id}")
def kb_delete_document(doc_id: str, x_user_id: Optional[str] = Header(default=None)):
    uid = get_user_id(x_user_id)
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM kb_documents WHERE id = ? AND (user_id = ? OR user_id = ?)",
            (doc_id, uid, KB_USER),
        )
        conn.execute("DELETE FROM kb_chunks WHERE doc_id = ?", (doc_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"ok": True}


@app.get("/api/kb/documents/{doc_id}")
def kb_get_document(doc_id: str, x_user_id: Optional[str] = Header(default=None)):
    """获取单个文档的完整内容（用于点击查看原文）。"""
    doc = _get_kb_document(get_user_id(x_user_id), doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@app.post("/api/kb/search")
def kb_search(req: KBQuery, x_user_id: Optional[str] = Header(default=None)):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="检索词不能为空")
    top_k = req.top_k or KB_TOP_K
    return {"data": _kb_search(get_user_id(x_user_id), query, top_k, req.library_id)}


@app.post("/api/kb/reindex")
def kb_reindex(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """重建向量索引（需管理员密码）：给所有缺少向量的分块重新生成 embedding。"""
    _require_admin(x_admin_password)
    if _load_embedding_model() is None:
        raise HTTPException(
            status_code=503,
            detail="向量检索未启用：未安装 onnxruntime/模型，或 KB_EMBED_ENABLED=false",
        )
    with _db() as conn:
        rows = conn.execute("SELECT id, content FROM kb_chunks WHERE vec IS NULL").fetchall()
    total = len(rows)
    if total == 0:
        return {"data": {"total": 0, "indexed": 0, "failed": 0}}
    indexed = 0
    failed = 0
    for i in range(0, total, KB_EMBED_BATCH):
        batch = rows[i : i + KB_EMBED_BATCH]
        vecs = _embed_texts([r["content"] for r in batch])
        if vecs is None:
            failed += len(batch)
            continue
        with _db() as conn:
            for r, v in zip(batch, vecs):
                conn.execute(
                    "UPDATE kb_chunks SET vec = ? WHERE id = ?", (v.tobytes(), r["id"])
                )
        indexed += len(batch)
    return {"data": {"total": total, "indexed": indexed, "failed": failed}}


# ---------------------------------------------------------------------------
# OCR 识别（可插拔引擎）
# ---------------------------------------------------------------------------
_ocr_cache: dict = {}


def _ocr_engine() -> str:
    """探测可用 OCR 引擎，返回引擎名；无则返回空串。"""
    if shutil.which("tesseract"):
        return "tesseract"
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import cv2  # noqa: F401  # rapidocr 依赖 opencv 做图像解码

        return "rapidocr"
    except ImportError:
        pass
    try:
        import paddleocr  # noqa: F401

        return "paddleocr"
    except ImportError:
        pass
    return ""


def _get_rapidocr():
    if "rapidocr" not in _ocr_cache:
        from rapidocr_onnxruntime import RapidOCR

        # 优先使用本地自定义模型（backend/vendor/rapidocr/），缺失则回退到包内置模型
        kwargs = {}
        try:
            model_dir = Path(OCR_MODEL_DIR)
            det = model_dir / "ch_PP-OCRv4_det_infer.onnx"
            cls = model_dir / "ch_ppocr_mobile_v2.0_cls_infer.onnx"
            rec = model_dir / "ch_PP-OCRv4_rec_infer.onnx"
            if det.is_file() and cls.is_file() and rec.is_file():
                kwargs = {
                    "det_model_path": str(det),
                    "cls_model_path": str(cls),
                    "rec_model_path": str(rec),
                }
        except Exception:
            kwargs = {}
        try:
            _ocr_cache["rapidocr"] = RapidOCR(**kwargs) if kwargs else RapidOCR()
        except TypeError:
            # 个别版本构造参数不兼容时，回退默认构造（使用包内置模型）
            _ocr_cache["rapidocr"] = RapidOCR()
    return _ocr_cache["rapidocr"]


def _rapidocr_text(out) -> str:
    """从 RapidOCR 推理结果提取文本，兼容两种返回结构。

    - 旧版 rapidocr_onnxruntime：返回 (result, elapse)，result 为
      [[box, text, score], ...] 或 None
    - 新版 rapidocr：返回 RapidOCROutput 对象，含 .txts 文本列表
    """
    if isinstance(out, (tuple, list)):
        result = out[0] if out else None
        if not result:
            return ""
        lines = []
        for line in result:
            if isinstance(line, (tuple, list)) and len(line) > 1:
                lines.append(str(line[1]))
        return "\n".join(lines)
    txts = getattr(out, "txts", None)
    if txts is None:
        txts = getattr(out, "text", None)
    if not txts:
        return ""
    return "\n".join(str(t) for t in txts if t)


def _decode_image(data: bytes):
    """解码图片字节为 BGR 数组；依赖缺失或解码失败返回 None。"""
    try:
        import numpy as np
        import cv2
    except ImportError:
        return None
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _ocr_array(img, engine: str) -> str:
    """对已解码的图像数组（BGR）执行 OCR，返回文本。"""
    if engine == "rapidocr":
        ocr = _get_rapidocr()
        return _rapidocr_text(ocr(img))

    if engine == "paddleocr":
        if "paddleocr" not in _ocr_cache:
            from paddleocr import PaddleOCR

            _ocr_cache["paddleocr"] = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        ocr = _ocr_cache["paddleocr"]
        result = ocr.ocr(img, cls=True)
        lines = []
        for page in result or []:
            for line in page or []:
                if line and len(line) > 1:
                    lines.append(line[1][0])
        return "\n".join(lines)

    if engine == "tesseract":
        import cv2

        ok, buf = cv2.imencode(".png", img)
        if not ok:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(buf.tobytes())
            tmp = f.name
        try:
            out = subprocess.run(
                ["tesseract", tmp, "stdout", "-l", "chi_sim+eng"],
                capture_output=True,
                timeout=120,
            )
            return out.stdout.decode("utf-8", errors="ignore")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return ""


def _ocr_image(data: bytes, engine: str) -> str:
    """用指定引擎识别图片文字。"""
    img = _decode_image(data)
    if img is None:
        return ""
    return _ocr_array(img, engine)


def _pdf_text_layer(data: bytes):
    """提取 PDF 文本层，返回 (页数, 每页文本列表)；依赖缺失或解析失败返回 (0, [])。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return 0, []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return 0, []
    try:
        pages = [(page.get_text() or "").strip() for page in doc]
    finally:
        doc.close()
    return len(pages), pages


def _ocr_pdf_scanned(data: bytes, engine: str, dpi: int = 200) -> str:
    """扫描型 PDF：逐页渲染成图片并 OCR，返回合并文本。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    results = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = _decode_image(pix.tobytes("png"))
            if img is None:
                continue
            text = _ocr_array(img, engine)
            if text.strip():
                results.append(text.strip())
    finally:
        doc.close()
    return "\n\n".join(results)


@app.get("/api/ocr/status")
def ocr_status():
    engine = _ocr_engine()
    return {"available": bool(engine), "engine": engine or None}


@app.post("/api/ocr")
async def ocr_recognize(file: UploadFile = File(...)):
    """上传图片或 PDF，识别/提取文字。"""
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    is_pdf = ext == "pdf"
    if ext not in IMAGE_EXTS and not is_pdf:
        raise HTTPException(
            status_code=422, detail="请上传图片（png/jpg/jpeg/bmp/tif 等）或 PDF 文件"
        )
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件过大")

    # PDF：优先提取文本层（文字型），文本层不足则逐页渲染 OCR（扫描型）
    if is_pdf:
        num_pages, page_texts = _pdf_text_layer(data)
        if num_pages == 0:
            raise HTTPException(status_code=422, detail="无法解析该 PDF 文件")
        text_layer_chars = sum(len(t) for t in page_texts)
        # 文本层字符足够 → 文字型 PDF，直接返回（无需 OCR 引擎）
        if text_layer_chars >= max(50, num_pages * 20):
            text = "\n\n".join(t for t in page_texts if t).strip()
            if text:
                return {
                    "filename": filename or "未命名",
                    "text": text,
                    "engine": "pymupdf",
                    "chars": len(text),
                }
        # 扫描型：需要 OCR 引擎逐页识别
        engine = _ocr_engine()
        if not engine:
            raise HTTPException(
                status_code=503,
                detail="该 PDF 为扫描件（无文本层），且服务器未安装 OCR 引擎",
            )
        text = _ocr_pdf_scanned(data, engine)
        if not text.strip():
            raise HTTPException(status_code=422, detail="未能识别出文字，请检查 PDF 清晰度")
        return {
            "filename": filename or "未命名",
            "text": text,
            "engine": engine,
            "chars": len(text),
        }

    # 图片
    engine = _ocr_engine()
    if not engine:
        raise HTTPException(
            status_code=503,
            detail="服务器未安装 OCR 引擎，请联系管理员部署 rapidocr_onnxruntime 或 tesseract",
        )
    text = _ocr_image(data, engine)
    if not text.strip():
        raise HTTPException(status_code=422, detail="未能识别出文字，请检查图片清晰度")
    return {
        "filename": filename or "未命名",
        "text": text,
        "engine": engine,
        "chars": len(text),
    }


# ---------------------------------------------------------------------------
# 系统管理接口
# ---------------------------------------------------------------------------
def _get_config_snapshot() -> dict:
    return {
        "VLLM_BASE_URL": VLLM_BASE_URL,
        "VLLM_MODEL": VLLM_MODEL,
        "TEMPERATURE": TEMPERATURE,
        "MAX_TOKENS": MAX_TOKENS,
        "ENABLE_THINKING": ENABLE_THINKING,
    }


def _require_admin(x_admin_password: Optional[str]) -> None:
    """校验管理员密码（X-Admin-Password 请求头），错误抛 403。"""
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="管理员密码错误")


@app.get("/api/admin/stats")
def admin_stats(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    _require_admin(x_admin_password)
    day_ms = 7 * 24 * 3600 * 1000
    since = _now_ms() - day_ms
    with _db() as conn:
        users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM conversations"
        ).fetchone()[0]
        convs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        kb_docs = conn.execute("SELECT COUNT(*) FROM kb_documents").fetchone()[0]
        kb_chunks = conn.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]
        week_convs = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE update_time >= ?", (since,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT update_time FROM conversations WHERE update_time >= ?", (since,)
        ).fetchall()
        # token 用量估算（中文约 1 字 ≈ 1.3 token）
        total_chars = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages"
        ).fetchone()[0]
        total_tokens = int(total_chars * 1.3)
        feedback_good = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE rating = 1"
        ).fetchone()[0]
        feedback_bad = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE rating = -1"
        ).fetchone()[0]
    daily = [0] * 7
    today = datetime.date.today()
    for r in rows:
        d = datetime.date.fromtimestamp(r["update_time"] / 1000)
        delta = (today - d).days
        if 0 <= delta < 7:
            daily[6 - delta] += 1
    return {
        "users": users,
        "conversations": convs,
        "messages": msgs,
        "kbDocuments": kb_docs,
        "kbChunks": kb_chunks,
        "weekConversations": week_convs,
        "dailyActive": daily,
        "totalTokens": total_tokens,
        "feedbackGood": feedback_good,
        "feedbackBad": feedback_bad,
    }


@app.get("/api/admin/conversations")
def admin_conversations(
    limit: int = 50,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    _require_admin(x_admin_password)
    limit = max(1, min(limit, 500))
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, user_id, title, create_time, update_time FROM conversations "
            "ORDER BY update_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {
        "data": [
            {
                "id": r["id"],
                "userId": r["user_id"],
                "title": r["title"],
                "createTime": r["create_time"],
                "updateTime": r["update_time"],
            }
            for r in rows
        ]
    }


@app.get("/api/admin/config")
def admin_get_config(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    _require_admin(x_admin_password)
    return {"data": _get_config_snapshot()}


@app.post("/api/admin/config")
def admin_set_config(
    req: AdminConfigRequest,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    _require_admin(x_admin_password)
    global TEMPERATURE, MAX_TOKENS
    if req.temperature is not None:
        TEMPERATURE = float(req.temperature)
    if req.max_tokens is not None:
        MAX_TOKENS = int(req.max_tokens)
    return {"data": _get_config_snapshot()}


@app.get("/api/admin/backup")
def admin_backup(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """下载数据库一致性备份（SQLite backup API 快照）。"""
    _require_admin(x_admin_password)
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
        src.close()
        with open(tmp_path, "rb") as f:
            data = f.read()
    except Exception:
        raise HTTPException(status_code=500, detail="备份失败")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    fname = f"changjian-zhida-backup-{datetime.date.today().isoformat()}.db"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/admin/kb-index-status")
def admin_kb_index_status(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """知识库向量索引状态：每个文档的已向量化分块数。"""
    _require_admin(x_admin_password)
    with _db() as conn:
        rows = conn.execute(
            "SELECT d.id, d.filename, d.library_id, l.name AS lib_name, d.chunk_count, "
            "  (SELECT COUNT(*) FROM kb_chunks c WHERE c.doc_id = d.id AND c.vec IS NOT NULL) AS vec_count "
            "FROM kb_documents d LEFT JOIN kb_libraries l ON d.library_id = l.id "
            "ORDER BY d.create_time DESC"
        ).fetchall()
    docs = [dict(r) for r in rows]
    return {
        "data": {
            "totalChunks": sum(d["chunk_count"] for d in docs),
            "indexedChunks": sum(d["vec_count"] for d in docs),
            "documents": docs,
        }
    }


@app.get("/api/admin/vllm-health")
async def admin_vllm_health(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """探测 vLLM 模型服务是否在线（优先 /health，降级 /v1/models）。"""
    _require_admin(x_admin_password)
    start = time.time()
    # 去掉 OpenAI 兼容的 /v1 前缀，得到根地址，用于访问 vLLM 自带的 /health 端点
    base = VLLM_BASE_URL.rsplit("/v1", 1)[0]
    urls = [f"{base}/health", f"{VLLM_BASE_URL}/models"]
    last_err = ""
    for url in urls:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
            ) as client:
                resp = await client.get(url)
            latency = round((time.time() - start) * 1000)
            if resp.status_code == 200:
                return {"online": True, "latencyMs": latency, "model": VLLM_MODEL}
            last_err = f"{url} -> HTTP {resp.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{url} -> {str(e)[:150]}"
    return {
        "online": False,
        "latencyMs": round((time.time() - start) * 1000),
        "detail": last_err,
    }


@app.get("/api/admin/conversations/{conv_id}/messages")
def admin_conversation_messages(
    conv_id: str,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """查看某会话的完整对话内容（合规审计用）。"""
    _require_admin(x_admin_password)
    with _db() as conn:
        conv = conn.execute(
            "SELECT id, user_id, title, create_time, update_time FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        rows = conn.execute(
            "SELECT id, role, content, attachments, create_time FROM messages "
            "WHERE conversation_id = ? ORDER BY create_time ASC",
            (conv_id,),
        ).fetchall()
    return {
        "data": {
            "id": conv["id"],
            "userId": conv["user_id"],
            "title": conv["title"],
            "createTime": conv["create_time"],
            "updateTime": conv["update_time"],
            "messages": [
                {
                    "id": r["id"],
                    "role": r["role"],
                    "content": r["content"],
                    "attachments": r["attachments"],
                    "createTime": r["create_time"],
                }
                for r in rows
            ],
        }
    }


@app.get("/api/admin/conversations/{conv_id}/export")
def admin_export_conversation(
    conv_id: str,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """导出某会话为纯文本文件。"""
    _require_admin(x_admin_password)
    with _db() as conn:
        conv = conn.execute(
            "SELECT title, user_id, create_time FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        rows = conn.execute(
            "SELECT role, content, create_time FROM messages "
            "WHERE conversation_id = ? ORDER BY create_time ASC",
            (conv_id,),
        ).fetchall()
    lines = [f"# {conv['title']}", f"用户: {conv['user_id']}", ""]
    for r in rows:
        role = "用户" if r["role"] == "user" else "助手"
        lines.append(f"【{role}】{r['content']}")
        lines.append("")
    text = "\n".join(lines)
    fname = f"conversation-{conv_id[:8]}.txt"
    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/admin/conversations/batch-delete")
def admin_batch_delete(
    req: BatchDeleteRequest,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """批量删除会话（含消息与反馈）。"""
    _require_admin(x_admin_password)
    with _db() as conn:
        for cid in req.ids:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
            conn.execute("DELETE FROM feedback WHERE conversation_id = ?", (cid,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
    return {"ok": True, "deleted": len(req.ids)}


@app.get("/api/admin/prompts")
def admin_get_prompts(
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """读取可编辑的提示词模板。"""
    _require_admin(x_admin_password)
    return {
        "data": {
            "system_prompt_default": _PROMPT_OVERRIDES.get("system_prompt_default") or DEFAULT_SYSTEM,
            "identity_notice": _PROMPT_OVERRIDES.get("identity_notice") or IDENTITY_NOTICE,
            "output_format_notice": _PROMPT_OVERRIDES.get("output_format_notice") or OUTPUT_FORMAT_NOTICE,
        }
    }


@app.post("/api/admin/prompts")
def admin_set_prompts(
    req: PromptsRequest,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    """更新提示词模板（写 sys_config + 更新内存缓存，立即生效）。"""
    _require_admin(x_admin_password)
    global _PROMPT_OVERRIDES
    updates: dict = {}
    if req.system_prompt_default is not None:
        updates["system_prompt_default"] = req.system_prompt_default
    if req.identity_notice is not None:
        updates["identity_notice"] = req.identity_notice
    if req.output_format_notice is not None:
        updates["output_format_notice"] = req.output_format_notice
    with _db() as conn:
        for k, v in updates.items():
            conn.execute(
                "INSERT INTO sys_config(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = ?",
                (k, v, v),
            )
    _PROMPT_OVERRIDES.update(updates)
    return {
        "data": {
            "system_prompt_default": _PROMPT_OVERRIDES.get("system_prompt_default") or DEFAULT_SYSTEM,
            "identity_notice": _PROMPT_OVERRIDES.get("identity_notice") or IDENTITY_NOTICE,
            "output_format_notice": _PROMPT_OVERRIDES.get("output_format_notice") or OUTPUT_FORMAT_NOTICE,
        }
    }


# ---------------------------------------------------------------------------
# 检护营商智能体（食品安全行政处罚监督线索筛查）
# ---------------------------------------------------------------------------
async def _vllm_complete(messages: list, max_tokens: int = 2048) -> str:
    """非流式调用 vLLM，返回完整文本（用于字段提取等结构化输出）。"""
    payload = {
        "model": VLLM_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
    ) as client:
        resp = await client.post(f"{VLLM_BASE_URL}/chat/completions", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"模型服务返回错误 {resp.status_code}：{resp.text[:300]}")
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def _ys_collision_lookup(credit_code: str) -> bool:
    """查询信用代码是否在小规模许可/备案表中。"""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM ys_collision WHERE credit_code = ?", (credit_code,)
        ).fetchone()
    return row is not None


async def _extract_fields_llm(text: str) -> list:
    """用 LLM 从文书文本提取字段，返回 list[dict]（可能一案多行为）。"""
    messages = [
        {"role": "system", "content": agent_yingshang.EXTRACT_SYSTEM},
        {"role": "user", "content": agent_yingshang.build_extract_prompt(text)},
    ]
    content = await _vllm_complete(messages)
    obj = agent_yingshang.parse_json_lenient(content)
    if not obj:
        raise HTTPException(status_code=502, detail="字段提取失败，请检查文书内容或稍后重试")
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    raise HTTPException(status_code=502, detail="字段提取结果格式异常")


@app.get("/api/agent/yingshang/status")
def ys_status():
    """检护营商智能体状态：主体碰撞数据量。"""
    with _db() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM ys_collision").fetchone()[0]
    return {"collisionCount": cnt}


@app.post("/api/agent/yingshang/import-collision")
async def ys_import_collision(file: UploadFile = File(...)):
    """导入市监局许可/备案表（xlsx），用于主体碰撞（机制五/六）。"""
    data = await file.read()
    rows = agent_yingshang.parse_collision_xlsx(data, file.filename or "")
    if not rows:
        raise HTTPException(status_code=422, detail="未解析到「统一社会信用代码」列，请确认表格格式")
    with _db() as conn:
        for code, name, source, detail in rows:
            conn.execute(
                "INSERT INTO ys_collision(credit_code, name, source, detail) VALUES (?,?,?,?) "
                "ON CONFLICT(credit_code) DO UPDATE SET name=excluded.name, "
                "source=excluded.source, detail=excluded.detail",
                (code, name, source, detail),
            )
    return {"ok": True, "imported": len(rows)}


@app.post("/api/agent/yingshang/screen")
async def ys_screen(
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    fields: Optional[str] = Form(default=None),
):
    """筛查：输入字段表（JSON/xlsx）或文书（文本/文件），输出两档线索清单。"""
    records: list = []
    # 1. 直接传字段 JSON
    if fields:
        try:
            parsed = json.loads(fields)
        except Exception:
            raise HTTPException(status_code=422, detail="fields 不是合法 JSON")
        records = parsed if isinstance(parsed, list) else [parsed]
    # 2. 上传文件：xlsx=字段表，doc/txt/pdf 等=文书
    if not records and file is not None:
        data = await file.read()
        fname = file.filename or ""
        ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        if ext in ("xlsx", "xls"):
            records = agent_yingshang.parse_fields_xlsx(data)
        else:
            text = extract_text(fname, data)
    # 3. 文书文本 -> LLM 提取字段
    if not records and text:
        records = await _extract_fields_llm(text.strip())

    if not records:
        raise HTTPException(status_code=422, detail="未提供有效的字段表或文书内容")

    hints = agent_yingshang.screen_records(records, _ys_collision_lookup)
    return {
        "data": {
            "total": len(records),
            "hintCount": len(hints),
            "hints": hints,
        }
    }


# ---------------------------------------------------------------------------
# 可选：托管前端构建产物
# ---------------------------------------------------------------------------
if STATIC_DIR and Path(STATIC_DIR).is_dir():
    static_dir = Path(STATIC_DIR).resolve()
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(static_dir / "index.html"))


# ---------------------------------------------------------------------------
# 启动时初始化数据库
# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "80")),
        reload=False,
    )
