#!/usr/bin/env bash
# 使い方: scripts/evaluate.sh [small|medium|large|モデル名]... [-- 評価オプション]
#   例: scripts/evaluate.sh small
#       scripts/evaluate.sh qwen3-coder:30b -- --runs 1 --tasks bugfix
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
targets=()
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then shift; break; fi
  targets+=("$1")
  shift
done
[ ${#targets[@]} -gt 0 ] || targets=(small)
require_ollama
models=$(expand_models "${targets[@]}")
pull_missing $models
python3 -m evals $models "$@"
