#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$ROOT"

VENV_DIR=".venv"

# Find a Python executable
if command -v python >/dev/null 2>&1; then
  SYSTEM_PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
  SYSTEM_PYTHON=python3
elif command -v py >/dev/null 2>&1; then
  SYSTEM_PYTHON="py -3"
else
  echo "Error: 找不到 Python，可尝试安装 Python 3.8+。"
  exit 1
fi

# Create virtual environment if missing
if [ ! -d "$VENV_DIR" ]; then
  echo "创建虚拟环境: $VENV_DIR"
  $SYSTEM_PYTHON -m venv "$VENV_DIR"
fi

PYTHON="$ROOT/$VENV_DIR/bin/python"
PIP="$ROOT/$VENV_DIR/bin/pip"

# Windows Git Bash support
if [ ! -x "$PYTHON" ]; then
  if [ -x "$ROOT/$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON="$ROOT/$VENV_DIR/Scripts/python.exe"
    PIP="$ROOT/$VENV_DIR/Scripts/pip.exe"
  fi
fi

if [ ! -x "$PYTHON" ]; then
  echo "Error: 虚拟环境中的 Python 未找到。请检查 $VENV_DIR 是否创建成功。"
  exit 1
fi

echo "使用 Python: $PYTHON"

echo "升级 pip 并安装依赖..."
"$PYTHON" -m pip install --upgrade pip
"$PIP" install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已生成 .env 文件，请编辑 .env 填写真实 API Key 后重新运行。"
  echo "  DASHSCOPE_API_KEY=your-real-key"
  echo "  GEMINI_API_KEY=your-real-key"
  exit 0
fi

if grep -Eq "DASHSCOPE_API_KEY=your|GEMINI_API_KEY=your" .env; then
  echo "警告: .env 中仍包含占位符 API Key，请确认已替换为真实值。"
fi

PORT=5001

echo "尝试启动服务: http://127.0.0.1:$PORT"
if ! "$PYTHON" app.py; then
  echo "端口 $PORT 可能被占用，尝试改用端口 5002..."
  "$PYTHON" -c "from app import app; app.run(host='0.0.0.0', port=5002, debug=True)"
fi
