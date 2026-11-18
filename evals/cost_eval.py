"""Eval 2 - cost: per-node and total cost for common tasks, actual vs theoretical (free models show 0 actual).

Usage: python evals/cost_eval.py --models "meta-llama/llama-3.3-70b-instruct:free,openai/gpt-4o-mini"
At least one paid model must be included (the script refuses otherwise).
"""
import argparse
import os

from _driver import TASKS, has_paid_rows, run_auto, write_csv  # must come first: sets sys.path
from agent import llm

DEFAULT = "meta-llama/llama-3.3-70b-instruct:free,openai/gpt-4o-mini"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.getenv("COST_MODELS", DEFAULT))
    ap.add_argument("--append", action="store_true", help="keep the successful rows already in the CSV; replace only the given models")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if all(m.endswith(":free") for m in models) and not (args.append and has_paid_rows("cost_eval.csv")):
        raise SystemExit("cost_eval needs at least one paid (non ':free') model")
    rows = []
    for model in models:
        for tid, task in TASKS.items():
            try:
                run_auto(task, model)
            except Exception as e:
                rows.append({"model": model, "task_id": tid, "node": "ERROR", "error": f"{type(e).__name__}: {e}"[:300]})
                continue
            for r in llm.TRACKER.by_node():
                rows.append({"model": model, "task_id": tid, "node": r["node"], "calls": r["calls"],
                             "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
                             "actual_usd": round(r["actual_usd"], 6), "theoretical_usd": round(r["theoretical_usd"], 6)})
            t = llm.TRACKER.total()
            rows.append({"model": model, "task_id": tid, "node": "TOTAL", "calls": t["calls"], "input_tokens": t["input_tokens"],
                         "output_tokens": t["output_tokens"], "actual_usd": round(t["actual_usd"], 6),
                         "theoretical_usd": round(t["theoretical_usd"], 6)})
            print(f"[eval] {model} / {tid}: actual ${t['actual_usd']:.5f} theoretical ${t['theoretical_usd']:.5f}")
    write_csv("cost_eval.csv", rows, append=args.append)


if __name__ == "__main__":
    main()
