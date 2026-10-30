"""Pre-submission check: python check_submission.py   (prints what is still missing for the course checklist; exit code 1 if anything is)."""
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
problems, warnings = [], []


def ok(msg):
    print(f"  OK   {msg}")


def bad(msg):
    problems.append(msg)
    print(f"  FIX  {msg}")


def warn(msg):
    warnings.append(msg)
    print(f"  WARN {msg}")


print("Structure")
for rel in ("agent/__init__.py", "agent/graph.py", "agent/nodes.py", "agent/tools.py", "agent/cli.py", "evals/compare_models.py", "evals/cost_eval.py",
            "evals/scope_eval.py", "evals/rubric.md", "manifest.json", "requirements.txt", "README.md", ".env.example"):
    ok(rel) if (ROOT / rel).is_file() else bad(f"missing file: {rel}")

print("manifest.json")
before = len(problems)
try:
    m = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    for k in ("name", "version", "description", "creator_name", "contact_information", "release_date", "repository_url", "download_url", "target_audience",
              "professional_fields", "tasks_capable_of_performing", "examples_of_suitable_questions", "technical_specifications"):
        if not m.get(k):
            bad(f"manifest.json: '{k}' is empty")
    if any(x in m.get("contact_information", "") for x in ("example.com", "your.")) or "@" not in m.get("contact_information", ""):
        bad("manifest.json: contact_information is still a placeholder - write a real email")
    if "username" in m.get("repository_url", "") or "username" in m.get("download_url", ""):
        bad("manifest.json: repository_url / download_url still contain 'username'")
    ok("manifest.json complete") if len(problems) == before else None
except Exception as e:  # noqa: BLE001
    bad(f"manifest.json is not valid JSON: {e}")

print("Secrets")
gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
ok(".env is git-ignored") if ".env" in gi.splitlines() else bad(".env is not in .gitignore")
try:
    tracked = subprocess.run(["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    bad(".env is tracked by git - remove it: git rm --cached .env") if tracked else ok(".env is not tracked")
except OSError:
    warn("git not found - could not check that .env is not tracked")
env = (ROOT / ".env.example").read_text(encoding="utf-8") if (ROOT / ".env.example").exists() else ""
for line in env.splitlines():
    if "KEY" in line and "=" in line and line.split("=", 1)[1].strip():
        bad(f".env.example contains a value for {line.split('=')[0]}")

print("Evals (CSV in evals/results, produced by a real run)")
for name, min_rows in (("compare_models.csv", 2), ("cost_eval.csv", 2), ("scope_eval.csv", 6)):
    p = ROOT / "evals" / "results" / name
    if not p.is_file():
        bad(f"{name} is missing - run: python evals/run_all.py")
        continue
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    errors = [r for r in rows if r.get("error")]
    if len(rows) < min_rows:
        bad(f"{name} has only {len(rows)} rows")
    elif errors:
        bad(f"{name}: {len(errors)} rows contain an error - fix the cause (key / credit / model) and re-run")
    else:
        ok(f"{name} ({len(rows)} rows)")

print("Distribution")
ok("dist/agent.exe built") if (ROOT / "dist" / "agent.exe").is_file() else warn("dist/agent.exe not built here - tag a release (see .github/workflows/release.yml) or run build_exe.bat on Windows")
ok("release workflow") if (ROOT / ".github" / "workflows" / "release.yml").is_file() else bad("missing .github/workflows/release.yml")

print(f"\n{len(problems)} to fix, {len(warnings)} warnings")
sys.exit(1 if problems else 0)
