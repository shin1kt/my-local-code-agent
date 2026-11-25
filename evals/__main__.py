from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from my_agent.config import Config, normalize_host
from my_agent.llm import LLMError, OllamaClient

from .harness import load_tasks, run_case


def summarize(results: list[dict], errors: dict[str, str], settings: str) -> str:
    models = list(dict.fromkeys(r["model"] for r in results))
    tasks = list(dict.fromkeys(r["task"] for r in results))
    out = ["# 評価結果", "", settings, "", "## モデル別", ""]
    out += ["| モデル | 合格 | 平均時間 | 平均ツール数 | ツールエラー | 拒否 | 生成速度 | GPU |", "|---|---|---|---|---|---|---|---|"]
    for m in models:
        rows = [r for r in results if r["model"] == m]
        n = len(rows)
        gpu = rows[0]["gpu_percent"]
        out.append(
            f"| {m} | {sum(r['passed'] for r in rows)}/{n} "
            f"| {sum(r['seconds'] for r in rows) / n:.0f}秒 "
            f"| {sum(r['tool_calls'] for r in rows) / n:.1f} "
            f"| {sum(r['tool_errors'] for r in rows)} | {sum(r['denied'] for r in rows)} "
            f"| {sum(r['tokens_per_second'] for r in rows) / n:.0f} tok/s "
            f"| {'不明' if gpu is None else f'{gpu}%'} |"
        )
    out += ["", "## 課題別(合格数/回数)", "", "| 課題 | " + " | ".join(models) + " |", "|---" * (len(models) + 1) + "|"]
    for t in tasks:
        cells = []
        for m in models:
            rows = [r for r in results if r["model"] == m and r["task"] == t]
            cells.append(f"{sum(r['passed'] for r in rows)}/{len(rows)}" if rows else "-")
        out.append(f"| {t} | " + " | ".join(cells) + " |")
    failures = Counter((r["model"], r["task"], r["status"], r["reason"]) for r in results if not r["passed"])
    if failures:
        out += ["", "## 不合格の内訳", ""]
        out += [f"- {m} / {t}: {s}、{r}({n}回)" for (m, t, s, r), n in failures.items()]
    if errors:
        out += ["", "## 実行できなかったモデル", ""] + [f"- {m}: {e}" for m, e in errors.items()]
    return "\n".join(out) + "\n"


def main() -> int:
    default = Config.from_env(Path.cwd())
    p = argparse.ArgumentParser(prog="evals", description="モデルごとにエージェントの成功率を測る")
    p.add_argument("models", nargs="+", help="Ollamaのモデル名")
    p.add_argument("--tasks", nargs="+", metavar="TASK", help="課題名(省略すると全部)")
    p.add_argument("--runs", type=int, default=3, help="課題ごとの繰り返し回数")
    p.add_argument("--timeout", type=int, default=600, help="1件あたりの制限時間(秒)")
    p.add_argument("--num-ctx", type=int, default=default.num_ctx)
    p.add_argument("--max-steps", type=int, default=default.max_steps)
    p.add_argument("--host", default=default.host)
    p.add_argument("--out", type=Path, help="結果の保存先")
    p.add_argument("--allow-all-commands", action="store_true", help="全コマンドを無条件に許可する(危険)")
    a = p.parse_args()
    try:
        tasks = load_tasks(a.tasks)
    except ValueError as e:
        p.error(str(e))

    out = a.out or Path("results") / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    settings = f"num_ctx={a.num_ctx} / max_steps={a.max_steps} / timeout={a.timeout}秒 / runs={a.runs}"
    results: list[dict] = []
    errors: dict[str, str] = {}

    def save() -> None:  # 途中で止めても結果が残るよう、1件ごとに保存する
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "summary.md").write_text(summarize(results, errors, settings), encoding="utf-8")

    try:
        for model in a.models:
            def make_llm(model: str = model) -> OllamaClient:
                return OllamaClient(normalize_host(a.host), model, a.num_ctx, default.temperature)

            print(f"\n=== {model} を読み込み中...", flush=True)
            llm = make_llm()
            try:
                llm.check_model()
                llm.load()
                gpu = llm.gpu_percent()
            except LLMError as e:
                print(f"スキップ: {e}")
                errors[model] = str(e)
                save()
                continue
            if gpu is not None and gpu < 100:
                print(f"注意: GPUに載っているのは {gpu}% です。遅い場合は小さいモデルか --num-ctx を下げて試してください")
            for task in tasks:
                for run in range(1, a.runs + 1):
                    print(f"{task.name} ({run}/{a.runs}) ... ", end="", flush=True)
                    log = out / f"{re.sub(r'[^A-Za-z0-9._-]', '_', model)}-{task.name}-{run}.log"
                    r = run_case(task, make_llm, log, a.num_ctx, a.max_steps, a.timeout, a.allow_all_commands)
                    results.append({"model": model, "run": run, "gpu_percent": gpu, **r})
                    save()
                    note = "" if r["passed"] else f" [{r['status']}] {r['reason']}"
                    print(f"{'合格' if r['passed'] else '不合格'} {r['seconds']}秒{note}", flush=True)
            try:
                llm.unload()  # 次のモデルのためにGPUメモリを空ける
            except LLMError:
                pass
    except KeyboardInterrupt:
        print("\n中断しました(ここまでの結果は保存済み)")
    if results or errors:
        print("\n" + (out / "summary.md").read_text(encoding="utf-8"))
    print(f"保存先: {out}")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
