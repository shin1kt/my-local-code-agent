# ローカルLLMコーディングエージェント(サンプル)

Ollama で動かすローカルLLMを使い、ファイルの調査・編集・コマンド実行を自律的に行う最小構成のエージェントです。
Python 標準ライブラリだけで書いてあり、`pip install` は不要です。

## 1. 準備

必要なもの: Python 3.10 以上、[Ollama](https://ollama.com/download)

```sh
ollama serve                # Ollama.app を起動済みなら不要
ollama pull qwen2.5:14b     # 既定のモデル(約9GB)
ollama show qwen2.5:14b     # Capabilities に tools があることを確認
```

## 2. 動作確認

```sh
python3 -m unittest discover -s tests -t .   # LLMなしで動くテスト
python3 -m my_agent "このプロジェクトの構成を説明して"
```

## 3. 試す・評価する

```sh
scripts/try.sh qwen2.5:14b                                  # 例題を承認しながら1回試す
scripts/evaluate.sh qwen2.5:14b -- --runs 1 --tasks bugfix  # 自動で評価する
```

Linux マシンで上位モデルを評価する手順は [docs/setup-linux.md](docs/setup-linux.md) に、課題と採点の内容は [docs/evaluation.md](docs/evaluation.md) にまとめています。

## 4. 使い方

依頼文を省略すると対話モードになります(`/clear` 会話リセット、`/exit` 終了、Ctrl-C 中断)。

| オプション | 環境変数 | 既定値 | 内容 |
|---|---|---|---|
| `-C`, `--workspace` | | カレント | 作業対象のディレクトリ |
| `-m`, `--model` | `MY_AGENT_MODEL` | `qwen2.5:14b` | モデル |
| `--host` | `OLLAMA_HOST` | `http://localhost:11434` | Ollama のURL |
| `--num-ctx` | `MY_AGENT_NUM_CTX` | `32768` | コンテキスト長。メモリ不足なら下げる |
| `--max-steps` | | `25` | 1回の依頼でLLMを呼ぶ上限 |
| `--yes` | | | 編集とコマンドを確認なしで許可 |

## 5. 仕組み

```
依頼 → LLM ─(ツール呼び出し)→ 承認 → ツール実行 → 結果をLLMへ ─┐
        ↑──────────────────────────────────────────────────────┘
        └(ツール呼び出しなし)→ 最終回答
```

| ファイル | 役割 |
|---|---|
| `my_agent/agent.py` | ループ本体とシステムプロンプト |
| `my_agent/llm.py` | Ollama API クライアント |
| `my_agent/tools.py` | ツール定義、パス制限 |
| `my_agent/context.py` | 会話をコンテキスト長に収める |
| `my_agent/ui.py` | 表示と承認 |
| `evals/` | 評価用の課題と採点 |
| `scripts/` | 環境確認、モデル取得、試行、評価 |

## 6. 安全上の注意

- ファイル操作はワークスペース内に限定されますが、**`run_command` は隔離されていません**。承認したコマンドはあなたの権限で何でもできます。
- `--yes` は使い捨てのコピーでだけ使ってください。普段は git 管理下で使い、差分を確認してください。

## 7. 現状の精度

評価ハーネスを作る前の試行(バグ修正の例題のみ、少数回)では、**テストを改変せずに例題を解けたモデルはありませんでした**。

| モデル | 結果 |
|---|---|
| `qwen2.5:14b` | テスト実行・編集・再実行までは進む。引用符を余分にエスケープして編集に失敗したり、テスト側を書き換えて通したりした |
| `qwen2.5:7b` | 調査だけで止まる(初期の版で確認) |
| `qwen2.5-coder:7b` | ツール呼び出しを説明文に混ぜて書くため、実行されない(初期の版で確認) |

上位モデルは未検証です。
