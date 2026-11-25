# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Ollama のローカルLLMで動くコーディングエージェントのサンプル。Python 3.10+、標準ライブラリのみ(依存を追加しない)。手順書 (`README.md`) は日本語で書く。

## コマンド

```sh
python3 -W error -m unittest discover -s tests -t .                       # 全テスト(Ollama不要)
python3 -m unittest tests.test_tools.ToolBoxTest.test_run_command         # 単一テスト
python3 -m my_agent -C <dir> "依頼"                                        # 実行(Ollama必要)
scripts/evaluate.sh <モデル> -- --runs 1 --tasks bugfix                    # 評価(Ollama必要)
```

ビルドとリンターはない。`evals/tasks/*/workspace` は意図的に未完成・バグ入りの課題なので直さない。

公開リポジトリなので、個人のパスやマシン情報を書かない。公開しないメモは `local/`、評価結果は `results/`(どちらも git 管理外)に置く。

## アーキテクチャ

`Agent.run` (`agent.py`) が、LLM呼び出し → ツール実行 → 結果を履歴に追加、をツール呼び出しがなくなるまで繰り返す。LLM と UI は Protocol で注入され、テストは台本どおりに応答する `FakeLLM` を使う。

- **エラーの流れ**: ツールは `ToolError` を送出し、`ToolBox.run` が `"ERROR: ..."` 文字列にして LLM に返す。`Agent` は結果の接頭辞 (`ERROR`, `DENIED`, `EXIT_CODE`) で成否を判定するため、これらの文言は `tools.py` と `agent.py` の間の契約になっている。
- **承認**: `Tool.preview` を持つツール = 副作用あり = 承認が必要。新しい書き込み系ツールには必ず `preview` を付ける。プレビューは `ui.printable` で制御文字を無害化して表示する。
- **パス制限**: ファイル系ツールは必ず `ToolBox._resolve` を通す。`run_command` は隔離されていない。
- **コンテキスト**: Ollama のネイティブAPIを使うのは、リクエストごとに `num_ctx` を指定するため(OpenAI互換APIに置き換えない)。`compact` は概算トークン数で履歴を縮め、最後の user メッセージ以降を残す。`NUDGE` も role は user だが、依頼とはみなさない。

## 評価 (`evals/`)

`run_case` が課題を一時ディレクトリにコピーして `Agent` を動かし、`grade` が別ディレクトリで非公開テスト (`hidden/`) を加えて採点する。`protected` のファイルを変更したら不合格。課題を追加したら `tests/test_evals.py` に正解例を足す(未着手で不合格、正解で合格を検査している)。評価中のコマンドは `is_safe_command` の許可リストで制限する。制限時間は SIGALRM なので並列実行できない。

スクリプトは Ubuntu 22.04 (Python 3.10) で動くこと。

## 小型モデル向けの対策

実測で見つかった失敗への対策なので、冗長に見えても理由なく外さない: システムプロンプトへのファイル一覧の埋め込み、`read_file` で行番号を付けない、編集時のインデントと Python 構文の検査 (`_edited`, `check_syntax`)、失敗後の続行促し (`NUDGE`)、同一呼び出しの抑止、本文に書かれたJSONの救済 (`parse_text_tool_calls`)。

## 既知の課題

- qwen2.5 系は例題でも不安定。引用符を余分にエスケープする (`\"\"\"`) ことへの対策がない。
- 1つの依頼の中で履歴が長くなった場合、`compact` は直近のツール結果や自分の応答までは縮めない。
