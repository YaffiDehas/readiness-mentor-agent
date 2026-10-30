"""Extensions: project scanner + BM25 RAG over the project's own files.

Everything here is read-only. The agent only ever reports files it actually found.
"""
import json
import re
from pathlib import Path

from rank_bm25 import BM25Plus  # BM25Okapi gives idf<=0 to terms found in half the chunks - bad for small projects

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".next",
             ".idea", ".vscode", "coverage", "Pods", ".gradle", "target"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
TEXT_EXT = {".md", ".txt", ".rst", ".adoc", ".json", ".yaml", ".yml", ".ts", ".tsx", ".js", ".jsx",
            ".py", ".graphql", ".gql", ".proto", ".java", ".kt", ".swift", ".cs", ".go", ".toml"}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
MAX_FILE_BYTES = 200_000
CHUNK, STEP = 1000, 800

_INDEX_CACHE: dict[str, "ProjectIndex"] = {}


def _walk(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS) and p.name not in SKIP_FILES:
            yield p.relative_to(root).as_posix()


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def detect_tech(root: Path, files: list[str]) -> list[str]:
    tech = []
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            tech += [f"npm:{name}" for name in list(deps)[:40]]
        except (json.JSONDecodeError, OSError):
            pass
    req = root / "requirements.txt"
    if req.exists():
        try:
            tech += [f"pip:{m.group(1)}" for ln in req.read_text(encoding="utf-8").splitlines() if (m := re.match(r"\s*([A-Za-z0-9_.\-]+)", ln)) and not ln.lstrip().startswith("#")][:40]
        except OSError:
            pass
    manifests = {"requirements.txt", "pyproject.toml", "tsconfig.json", "pom.xml", "build.gradle", "Podfile"}
    tech += [f"manifest:{f}" for f in files if f in manifests]
    return tech


_CONVENTIONS = [  # (what, filename regex) - tooling that defines how code must be written here
    ("lint rules", r"(^|/)(\.eslintrc[^/]*|eslint\.config\.[cm]?[jt]s|\.pylintrc|ruff\.toml|\.flake8)$"),
    ("formatting", r"(^|/)(\.prettierrc[^/]*|prettier\.config\.[cm]?js|\.editorconfig)$"),
    ("TypeScript config", r"(^|/)tsconfig[^/]*\.json$"),
    ("test setup", r"(^|/)(jest\.config[^/]*|vitest\.config[^/]*|pytest\.ini|setup[Tt]ests\.[jt]s)$"),
    ("component docs (Storybook)", r"(^|/)\.storybook/|\.stories\.[jt]sx?$"),
    ("contribution / style guide", r"(^|/)(CONTRIBUTING|STYLE[-_ ]?GUIDE|CODING[-_ ]?(STYLE|STANDARDS)|CONVENTIONS)[^/]*\.(md|rst|txt)$"),
]


def detect_conventions(files: list[str]) -> list[dict]:
    """Files that define how code is written in this project (lint, format, types, tests, style guide). Found by the agent itself - never asked."""
    out = []
    for what, rx in _CONVENTIONS:
        hits = [f for f in files if re.search(rx, f, re.I)]
        if hits:
            out.append({"what": what, "files": hits[:4]})
    return out


def is_agent_repo(base: Path) -> bool:
    """The agent's own source tree. It is never the project the developer works on - scanning it would ground the brief in files that do not belong to them."""
    return (base / "agent" / "arch.py").is_file() and (base / "agent" / "graph.py").is_file() and (base / "manifest.json").is_file()


def resolve_root(root) -> tuple[str, bool]:
    """-> (project root, was_agent_repo). "" means: NO project - nothing is scanned and nothing may be claimed about the code."""
    if root is None or not str(root).strip():
        return "", False
    base = Path(str(root).strip()).expanduser().resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"Project path not found: {base}")
    if is_agent_repo(base):
        return "", True
    return str(base), False


def scan_project(root: str) -> dict:
    if not root:
        return {"root": "", "no_project": True, "files": [], "n_files": 0, "top_dirs": [], "docs": [], "api": [], "tests": [], "tech": [], "conventions": []}
    base = Path(root).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"Project path not found: {base}")
    files = list(_walk(base))
    return {
        "root": str(base),
        "files": files,
        "n_files": len(files),
        "top_dirs": sorted({f.split("/")[0] for f in files if "/" in f}),
        "docs": [f for f in files if Path(f).suffix.lower() in DOC_EXT],
        "api": [f for f in files if re.search(r"swagger|openapi|api[-_]?docs", f, re.I)
                or Path(f).suffix.lower() in {".graphql", ".gql", ".proto"}],
        "tests": [f for f in files if re.search(r"(^|/)(__tests__|tests?)(/|$)|\.(test|spec)\.[jt]sx?$|(^|/)test_.*\.py$", f)],
        "tech": detect_tech(base, files),
        "conventions": detect_conventions(files),
    }


def facts_text(scan: dict) -> str:
    if scan.get("no_project"):
        return ("NO PROJECT WAS PROVIDED: nothing was scanned. There are no project files, dependencies or conventions to rely on. "
                "Everything known about the project comes from the developer's own answers and is unverified.")
    def lst(items, n):
        return ", ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "") if items else "none found"
    return (f"files scanned: {scan['n_files']}\n"
            f"top-level dirs: {lst(scan['top_dirs'], 15)}\n"
            f"technologies detected (from manifests): {lst(scan['tech'], 40)}\n"
            f"documentation files: {lst(scan['docs'], 30)}\n"
            f"API contract candidates (swagger/openapi/graphql/proto): {lst(scan['api'], 15)}\n"
            f"test files: {lst(scan['tests'], 8)}\n"
            f"code conventions found (lint/format/types/tests/style guide): {lst([c['what'] + ' -> ' + ', '.join(c['files']) for c in scan.get('conventions', [])], 6)}")


class ProjectIndex:
    def __init__(self, root: str):
        self.root = Path(root).resolve() if root else None
        self.chunks: list[dict] = []
        for rel in (_walk(self.root) if self.root else []):
            p = self.root / rel
            if p.suffix.lower() not in TEXT_EXT or p.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i in range(0, max(len(text), 1), STEP):
                self.chunks.append({"path": rel, "text": text[i:i + CHUNK]})
        self.bm25 = BM25Plus([_tokens(c["path"] + " " + c["text"]) for c in self.chunks]) if self.chunks else None

    def search(self, query: str, k: int = 8, only: set[str] | None = None) -> list[dict]:
        """Top-k chunks; at most 2 per file so one big file cannot crowd out the rest."""
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(_tokens(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out, per_file = [], {}
        for i in order:
            c = self.chunks[i]
            if scores[i] <= 0 or (only is not None and c["path"] not in only):
                continue
            if per_file.get(c["path"], 0) >= 2:
                continue
            per_file[c["path"]] = per_file.get(c["path"], 0) + 1
            out.append({**c, "score": float(scores[i])})
            if len(out) == k:
                break
        return out


def get_index(root: str) -> ProjectIndex:
    key = str(Path(root).resolve()) if root else ""
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = ProjectIndex(key)
    return _INDEX_CACHE[key]


def evidence_text(hits: list[dict], limit: int = 600) -> str:
    return "\n\n".join(f"### {h['path']}\n{h['text'][:limit]}" for h in hits) or "(no matching files found)"


def read_project_file(root: str, rel: str, limit: int = 3000) -> str:
    if not root:
        return ""
    base = Path(root).resolve()
    p = (base / rel).resolve()
    if base not in p.parents:  # never read outside the project
        return ""
    try:
        return p.read_text(encoding="utf-8")[:limit]
    except (OSError, UnicodeDecodeError):
        return ""


def read_attachment(path: str, limit: int = 20_000) -> str:
    """Read a local file given by the user (task description, spec...). txt/md/code/json/docx."""
    p = Path(path.strip().strip('"')).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    if p.suffix.lower() == ".docx":
        from docx import Document
        doc = Document(str(p))
        parts = [para.text for para in doc.paragraphs]
        for table in doc.tables:
            parts += [" | ".join(c.text for c in row.cells) for row in table.rows]
        return "\n".join(parts)[:limit]
    try:
        return p.read_text(encoding="utf-8")[:limit]
    except UnicodeDecodeError:
        raise ValueError(f"Unsupported file (not text/docx): {p.name}")


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def is_readable(root: str, rel: str) -> bool:
    if not root:
        return False
    base = Path(root).resolve()
    p = (base / rel).resolve()
    return base in p.parents and p.is_file() and bool(read_project_file(root, rel, limit=1) or p.stat().st_size == 0)


def locate_quote(root: str, rel: str, quote: str) -> tuple[int, int] | None:
    """Return (first_line, last_line), 1-based, if `quote` literally occurs in the file (whitespace-insensitive), else None."""
    text = read_project_file(root, rel, limit=MAX_FILE_BYTES)
    if not quote.strip() or norm_text(quote) not in norm_text(text):
        return None
    lines = text.splitlines()
    first = next((i for i, ln in enumerate(lines, 1) if ln.strip() and norm_text(ln) in norm_text(quote)), None)
    if first is None:  # quote starts mid-line: fall back to the line containing its first words
        head = norm_text(quote)[:40]
        first = next((i for i, ln in enumerate(lines, 1) if head in norm_text(ln)), 1)
    return first, min(len(lines), first + quote.count("\n"))
