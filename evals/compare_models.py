"""Eval 1 - model comparison: same tasks, different models. Time, judge quality/reliability, cost -> CSV.

Usage: python evals/compare_models.py --models "meta-llama/llama-3.3-70b-instruct:free,openai/gpt-4o-mini"
"""
import argparse
import os

from _driver import CRITERIA, JUDGE_MODEL, TASKS, deterministic_metrics, judge, run_auto, write_csv

DEFAULT = "meta-llama/llama-3.3-70b-instruct:free,openai/gpt-4o-mini"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.getenv("EVAL_MODELS", DEFAULT))
    ap.add_argument("--append", action="store_true", help="keep the successful rows already in the CSV; replace only the given models")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    rows = []
    for model in models:
        for tid, task in TASKS.items():
            row = {"model": model, "task_id": tid, "judge_model": JUDGE_MODEL}
            try:
                state, seconds, cost = run_auto(task, model)  # snapshot before the judge adds its own calls
                scores = judge(task, state.get("final_prompt", ""))
                avg = sum(scores[k] for k in CRITERIA) / len(CRITERIA)
                row.update(seconds=round(seconds, 1), **deterministic_metrics(state), **{k: scores[k] for k in CRITERIA},
                           avg_quality=round(avg, 2), judge_comment=scores["comment"],
                           tokens=cost["input_tokens"] + cost["output_tokens"],
                           actual_usd=round(cost["actual_usd"], 6), theoretical_usd=round(cost["theoretical_usd"], 6))
            except Exception as e:  # keep going - a failing free model must not kill the whole eval
                row["error"] = f"{type(e).__name__}: {e}"[:300]
            print(f"[eval] {model} / {tid}: {row.get('avg_quality', row.get('error'))}")
            rows.append(row)
    write_csv("compare_models.csv", rows, append=args.append)


if __name__ == "__main__":
    main()
