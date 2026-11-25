#!/usr/bin/env bash
# 環境確認。何も変更しない。
set -uo pipefail
cd "$(dirname "$0")/.."
ng=0
ok() { echo "[OK] $*"; }
bad() { echo "[NG] $*"; ng=1; }

echo "== OS =="
[ -r /etc/os-release ] && (. /etc/os-release; echo "$PRETTY_NAME")
uname -srm

echo "== 必要なコマンド =="
for c in git curl python3; do
  if command -v "$c" >/dev/null; then ok "$c"; else bad "$c がありません: sudo apt install $c"; fi
done
if command -v python3 >/dev/null; then
  if python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then ok "$(python3 --version)"
  else bad "$(python3 --version) は古いため使えません(3.10 以上が必要)"; fi
fi
if command -v ollama >/dev/null; then ok "ollama"; else bad "ollama コマンドがありません"; fi

echo "== メモリ =="
command -v free >/dev/null && free -h
echo "== ディスク(モデルの保存先は通常 /usr/share/ollama か ~/.ollama)=="
df -h / "$HOME" 2>/dev/null
echo "== GPU =="
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv
elif command -v rocm-smi >/dev/null; then
  rocm-smi --showproductname --showmeminfo vram
else
  echo "nvidia-smi / rocm-smi がありません(統合メモリ機やGPUなしの場合は正常です)"
fi

echo "== Ollama =="
if command -v python3 >/dev/null && command -v curl >/dev/null; then
  url="$(python3 -c 'from my_agent.config import Config; from pathlib import Path; print(Config.from_env(Path(".")).host)' 2>/dev/null)"
  if version="$(curl -fsS --noproxy '*' -m 5 "$url/api/version" 2>/dev/null)"; then
    ok "$url に接続 $version"
    command -v ollama >/dev/null && ollama list
  else
    bad "$url に接続できません: sudo systemctl start ollama(または ollama serve)"
  fi
fi

echo "== ユニットテスト(LLM不要)=="
if python3 -m unittest discover -s tests -t . >/dev/null 2>&1; then ok "成功"
else bad "失敗: python3 -m unittest discover -s tests -t . で詳細を確認"; fi

echo
if [ "$ng" = 0 ]; then echo "準備OKです"; else echo "[NG] の項目を直してください"; fi
exit "$ng"
