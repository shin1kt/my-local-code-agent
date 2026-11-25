# 各スクリプトから読み込む共通設定
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OLLAMA_URL="$(python3 -c 'from my_agent.config import Config; from pathlib import Path; print(Config.from_env(Path(".")).host)')"

# モデルのセット。サイズはダウンロード量の目安。
models_small="qwen3-coder:30b gpt-oss:20b devstral-small-2:24b"  # 19 + 14 + 15 GB
models_medium="qwen3.6:35b qwen3-coder-next:latest"              # 23 + 52 GB
models_large="gpt-oss:120b devstral-2:123b"                      # 65 + 75 GB

# セット名(small/medium/large)をモデル名に展開する。それ以外はそのまま返す。
expand_models() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      small) echo $models_small ;;
      medium) echo $models_medium ;;
      large) echo $models_large ;;
      *) echo "$arg" ;;
    esac
  done
}

require_ollama() {
  if ! curl -fsS --noproxy '*' -m 5 "$OLLAMA_URL/api/version" >/dev/null; then
    echo "Ollama ($OLLAMA_URL) に接続できません。'sudo systemctl start ollama' か 'ollama serve' で起動してください。" >&2
    exit 1
  fi
}

# 未取得のモデルだけダウンロードする
pull_missing() {
  local model
  for model in "$@"; do
    if curl -fsS --noproxy '*' -m 10 "$OLLAMA_URL/api/show" -d "{\"model\":\"$model\"}" >/dev/null 2>&1; then
      echo "取得済み: $model"
    else
      echo "ダウンロード: $model"
      ollama pull "$model" || echo "取得に失敗しました: $model" >&2  # 残りのモデルは続ける
    fi
  done
}
