#!/usr/bin/env bash
# ============================================================
# 昌检智答AI助手 — 离线一键部署脚本（无需公网 / 无需 nginx）
# 适用：openEuler aarch64、Python 3.9+
# 用法：把整个 changjian-zhida 目录放到服务器后执行：
#   cd /opt/changjian-zhida && bash deploy/install.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$APP_DIR/backend"
DIST_DIR="$APP_DIR/dist"

echo "=================================================="
echo " 昌检智答AI助手 离线部署"
echo " 应用目录: $APP_DIR"
echo "=================================================="

# ---------- 1. 检查 Python ----------
if ! command -v python3 >/dev/null 2>&1; then
  echo "!! 未找到 python3，请先安装 Python 3.9+"
  exit 1
fi
echo "[1/5] Python 版本: $(python3 --version)"

# 确保 pip 可用
python3 -m pip --version >/dev/null 2>&1 || python3 -m ensurepip --upgrade >/dev/null 2>&1 || true

# ---------- 2. 离线安装依赖 ----------
echo "[2/5] 离线安装 Python 依赖（wheel 包）..."
cd "$BACKEND_DIR"
python3 -m pip install --no-index --find-links "$BACKEND_DIR/wheels" -r requirements.txt

# OCR 可选依赖（RapidOCR）：若 wheel 已打包则安装，缺失则跳过（/api/ocr 返回 503 友好提示）
if [ -f "$BACKEND_DIR/requirements-ocr.txt" ]; then
  echo "     安装 OCR 可选依赖（RapidOCR）..."
  # 注意：rapidocr_onnxruntime 声明依赖 opencv-python，本项目用 opencv-python-headless 替代
  # （服务器无 GUI，headless 不依赖 libGL 等系统库）。二者是不同包名，pip 无法自动替代，
  # 故必须加 --no-deps 跳过依赖解析——所有依赖已显式列在 requirements-ocr.txt 中。
  if python3 -m pip install --no-index --find-links "$BACKEND_DIR/wheels" --no-deps -r "$BACKEND_DIR/requirements-ocr.txt"; then
    echo "     OCR 引擎已就绪"
  else
    echo "     !! OCR 依赖安装失败（不影响主功能，/api/ocr 将返回 503）"
  fi
fi

# ---------- 3. 生成 .env ----------
echo "[3/5] 生成配置文件 .env..."
if [ ! -f "$BACKEND_DIR/.env" ]; then
  cat > "$BACKEND_DIR/.env" <<EOF
VLLM_BASE_URL=http://143.9.233.5:8000/v1
VLLM_MODEL=Qwen3.6_35B_A3B
DB_PATH=$BACKEND_DIR/chat.db
STATIC_DIR=$DIST_DIR
HOST=0.0.0.0
PORT=80
ENABLE_THINKING=false
MAX_UPLOAD_BYTES=20
MAX_UPLOAD_CHARS=20000
KB_CHUNK_SIZE=500
KB_CHUNK_OVERLAP=50
KB_TOP_K=5
KB_MAX_DOC_CHARS=200000
KB_EMBED_ENABLED=true
EOF
  echo "    已生成 .env（后端直接监听 80 端口并托管前端）"
else
  echo "    .env 已存在，跳过（如需修改请编辑 $BACKEND_DIR/.env）"
fi

# ---------- 4. 生成并注册 systemd 服务 ----------
echo "[4/5] 配置 systemd 服务..."
PYBIN="$(command -v python3)"
SERVICE_FILE="/etc/systemd/system/changjian-zhida.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Changjian Zhida Backend (FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=$BACKEND_DIR
ExecStart=$PYBIN -m uvicorn main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable changjian-zhida >/dev/null 2>&1 || true
systemctl restart changjian-zhida

# ---------- 5. 验证 ----------
echo "[5/5] 验证服务..."
sleep 3
echo -n "    后端健康检查: "
curl -s --max-time 5 http://127.0.0.1:80/api/health && echo "" || echo "失败（查看 journalctl -u changjian-zhida -f）"

echo ""
echo "=================================================="
echo " 部署完成！"
echo " 访问地址: http://$(hostname -I 2>/dev/null | awk '{print $1}')/"
echo " 后端日志: journalctl -u changjian-zhida -f"
echo " 配置修改: $BACKEND_DIR/.env（改后 systemctl restart changjian-zhida）"
echo ""
echo " 若 80 端口被占用，编辑 $BACKEND_DIR/.env 里的 PORT，"
echo " 并同步修改 $SERVICE_FILE 里的 --port，然后重启服务。"
echo "=================================================="
