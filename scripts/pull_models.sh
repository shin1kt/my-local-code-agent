#!/usr/bin/env bash
# 使い方: scripts/pull_models.sh [small|medium|large|モデル名]...
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_ollama
pull_missing $(expand_models "${@:-small}")
ollama list
