"""Runs the three evals one after the other and lists the CSV files (needs OPENROUTER_API_KEY, and credit for at least one paid model).
python evals/run_all.py [--models "meta-llama/llama-3.3-70b-instruct:free,openai/gpt-4o-mini"]"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


def main() -> int:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.getenv("EVAL_MODELS", "meta-llama/llama-3.3-70b-instruct:free,openai/gpt-4o-mini"),
                    help="models for the comparison eval (include at least one paid model)")
    args = ap.parse_args()
    if not os.getenv("OPENROUTER_API_KEY"):
        print("[ERROR] OPENROUTER_API_KEY is not set (copy .env.example to .env).")
        return 2
    failed = []
    for name, extra in (("compare_models.py", ["--models", args.models]), ("cost_eval.py", []), ("scope_eval.py", [])):
        print(f"\n===== {name} =====")
        if subprocess.call([sys.executable, str(HERE / name), *extra]) != 0:
            failed.append(name)
    print("\nResults:")
    for p in sorted((HERE / "results").glob("*.csv")):
        print(f"  {p.relative_to(HERE.parent)}  ({p.stat().st_size} bytes)")
    print("\nNext: python check_submission.py")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
