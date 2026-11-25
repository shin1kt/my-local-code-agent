# Linux(Ubuntu)で上位モデルを評価する手順

Ollama 導入済みの Ubuntu 22.04 以降を想定しています。追加の Python パッケージは不要です。

## 1. clone する

```sh
sudo apt update && sudo apt install -y git curl python3   # 入っていれば不要
git clone https://github.com/shin1kt/my-local-code-agent.git
cd my-local-code-agent
```

## 2. 環境を確認する

```sh
scripts/check_env.sh
```

最後に「準備OKです」と出れば次へ進みます。何も変更しないので、何度実行しても構いません。

Ollama に接続できないとき:

```sh
sudo systemctl start ollama          # サービスとして入っている場合
systemctl status ollama --no-pager
ollama serve                         # サービスがない場合(別の端末で起動したままにする)
```

Ollama が古いと新しいモデルを取得できないことがあります。その場合は[公式の手順](https://ollama.com/download/linux)で更新してください。

## 3. モデルをダウンロードする

GPUメモリ(統合メモリ機なら使える総メモリ)に合わせて選びます。ダウンロード量に加え、コンテキスト用に数GB以上の余裕が必要です。

| セット | モデル(ダウンロード量) | メモリの目安 |
|---|---|---|
| `small` | `qwen3-coder:30b` (19GB), `gpt-oss:20b` (14GB), `devstral-small-2:24b` (15GB) | 24GB〜 |
| `medium` | `qwen3.6:35b` (23GB), `qwen3-coder-next:latest` (52GB) | 32GB〜 / 64GB〜 |
| `large` | `gpt-oss:120b` (65GB), `devstral-2:123b` (75GB) | 96GB〜 |

```sh
scripts/pull_models.sh qwen3-coder:30b   # まず1つだけ
scripts/pull_models.sh small             # セットでまとめて(計約48GB)
scripts/pull_models.sh small medium      # 複数指定も可
```

取得済みのモデルは飛ばします。途中で切れても、再実行すれば続きから再開します。

## 4. 試す

```sh
scripts/try.sh qwen3-coder:30b           # バグ修正の例題
scripts/try.sh qwen3-coder:30b from_spec # 別の課題
```

編集やコマンド実行のたびに確認が出ます。内容を見て `y` で進めてください。例題のコピーに対して動き、最後に変更点と採点結果を表示します。

課題: `bugfix`, `feature`, `rename`, `cross_file_bug`, `from_spec`

## 5. 評価する

まず1課題・1回だけ動かし、時間の見当をつけます。

```sh
scripts/evaluate.sh qwen3-coder:30b -- --runs 1 --tasks bugfix
```

問題なければ本番です。既定では5課題を3回ずつ、1件最大10分なので、**1モデルあたり最大2.5時間**かかります。SSH が切れても続くように、`tmux` か `nohup` で実行します。

```sh
nohup scripts/evaluate.sh small > eval.out 2>&1 &
tail -f eval.out          # 進み具合(Ctrl-C で表示だけ終了)
nvidia-smi -l 5           # GPU の使用状況(別の端末で)
```

未取得のモデルは自動でダウンロードします。

| オプション(`--` の後) | 既定値 | 内容 |
|---|---|---|
| `--runs N` | 3 | 課題ごとの回数 |
| `--tasks 名前...` | 全部 | 課題を絞る |
| `--timeout 秒` | 600 | 1件の制限時間。大きいモデルで時間切れになるなら延ばす |
| `--num-ctx N` | 32768 | コンテキスト長。GPUに載らないなら下げる |
| `--max-steps N` | 25 | LLM呼び出しの上限 |
| `--allow-all-commands` | なし | コマンドを無条件で許可する(危険。通常は不要) |

### 結果の見方

```sh
cat "$(ls -d results/*/ | tail -1)summary.md"
```

- `summary.md`: 合格数、時間、生成速度の表
- `results.json`: 1件ごとの数値
- `*.log`: やりとりの全文
- `*.diff`: モデルが行った変更

表の「GPU」が 100% でない場合、モデルの一部が CPU で動いており大幅に遅くなります。「拒否」は許可リスト外のコマンドを止めた回数です。

採点は成果物を別の場所にコピーし、非公開テストを加えて行います。テストや仕様書を書き換えた場合は不合格です。時間切れやステップ上限で終わっても、その時点の成果物が正しければ合格として数えます(`results.json` の `status` で区別できます)。課題と採点の詳細は [evaluation.md](evaluation.md) を参照してください。

### 安全について

評価は承認なしで進みます。ファイル編集は課題の一時コピー内に限られ、コマンドは許可リスト(テスト実行、`ls`、`cat` など)だけが通ります。ただし **モデルが書いた Python コードは、テスト実行時に現在のユーザー権限で動きます**。気になる場合は、専用ユーザーやコンテナで実行してください。

## 片付け

```sh
ollama ps                    # 読み込み中のモデル
ollama stop qwen3-coder:30b  # メモリから降ろす
ollama rm qwen3-coder:30b    # ディスクから削除
```
