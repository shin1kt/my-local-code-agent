#!/usr/bin/env bash
# 例題をコピーし、承認しながら1回試す。使い方: scripts/try.sh [モデル名] [課題名]
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
model="${1:-qwen3-coder:30b}"
task="${2:-bugfix}"
if [ ! -d "evals/tasks/$task/workspace" ]; then
  echo "課題がありません: $task(使える課題: $(ls evals/tasks | xargs))" >&2
  exit 1
fi
require_ollama
pull_missing "$model"
work="$(mktemp -d)"
cp -R "evals/tasks/$task/workspace/." "$work/"
prompt="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["prompt"])' "evals/tasks/$task/task.json")"
echo "作業ディレクトリ: $work"
echo "依頼: $prompt"
echo
status=0
python3 -m my_agent -C "$work" -m "$model" "$prompt" || status=$?
echo
echo "== 変更点 =="
diff -ru -x __pycache__ "evals/tasks/$task/workspace" "$work" || true
echo "== 採点 =="
python3 - "$task" "$work" <<'PY'
import sys
from pathlib import Path
from evals.harness import grade, load_tasks
passed, reason = grade(load_tasks([sys.argv[1]])[0], Path(sys.argv[2]))
print("合格" if passed else f"不合格: {reason}")
PY
exit "$status"
