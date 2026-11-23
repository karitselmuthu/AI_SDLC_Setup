"""Review adapters: which kinds of code a change touches, found from repository evidence (file names, manifests, added lines), and what to focus on.
Plain code, no model. A technology with no adapter is disclosed as unsupported, never assumed to be reviewable.
detect(repo, files, diff) -> dict(areas=[dict(area, focus, evidence)], unsupported=[dict(what, why)])   render(det)   prompt_note(det)
"""
import json
import pathlib
import re

FOCUS = {
    "Frontend": "state and rendering logic, unsafe browser behaviour (innerHTML, eval), accessibility, input handling, client-side secrets",
    "Backend": "business logic, authorization, validation, error handling, concurrency, API behaviour",
    "Mobile and desktop": "permissions, sensitive storage, platform behaviour, accessibility, secure communication",
    "Data and databases": "query safety (injection), schema changes, data integrity, sensitive data, migration compatibility",
    "Integration and messaging": "contract compatibility, authentication, retries, idempotency, ordering, failure handling",
    "Infrastructure and delivery": "permissions, exposed endpoints, secret handling, insecure defaults, scaling and cost implications",
    "AI and data applications": "data exposure, access boundaries, unsafe tool use, evaluation assumptions, logging, resource cost",
    "Cross-cutting": "maintainability, reliability, observability, privacy, policy alignment, evidence quality",
}
UI = re.compile(r"(?i)\.(jsx|tsx|vue|svelte|html?|css|scss)$")
SERVER = re.compile(r"(?i)\.(py|java|kt|cs|go|rs|php|rb|scala|js|mjs|ts)$")
MOBILE = re.compile(r"(?i)(androidmanifest\.xml|info\.plist|pubspec\.yaml|\.swift$|\.dart$|\.storyboard$|\.xib$)")
SQL = re.compile(r"(?i)\.sql$|(^|/)(migrations?|alembic|db/migrate)/|schema\.(rb|prisma)$|\.prisma$")
IFACE = re.compile(r"(?i)(openapi|swagger|asyncapi)[^/]*\.(ya?ml|json)$|\.(graphql|gql|proto|avsc)$")
INFRA = re.compile(r"(?i)(\.tf$|\.tfvars$|(^|/)dockerfile|docker-compose|(^|/)chart\.ya?ml$|(^|/)values\.ya?ml$|serverless\.ya?ml$|template\.ya?ml$|pulumi|cdk\.json|\.github/workflows/|kustomization)")
# keywords in ADDED lines
KW = {
    "Frontend": r"(?i)\binnerHTML\b|dangerouslySetInnerHTML|document\.(write|cookie)|localStorage|useState|addEventListener|v-html",
    "Mobile and desktop": r"(?i)android\.permission|SharedPreferences|UserDefaults|Keychain|ipcRenderer|BrowserWindow|react-native",
    "Data and databases": r"(?i)\bSELECT\b[^\n]{1,80}\bFROM\b|\bINSERT INTO\b|\bUPDATE\s+\w+\s+SET\b|\bDELETE FROM\b|\bCREATE TABLE\b|\bALTER TABLE\b|cursor\.execute|\.query\(|sqlalchemy|pymongo|mongoose|\bredis\b|psycopg|jdbc",
    "Integration and messaging": r"(?i)webhook|kafka|rabbitmq|\bsqs\b|\bsns\b|pubsub|grpc|graphql|idempot|\bretry\b|requests\.(get|post)|fetch\(|httpx|axios|@app\.route|@(Get|Post)Mapping|express\(",
    "AI and data applications": r"(?i)anthropic|openai|langchain|llama|embedding|vector ?(store|db|database)|vectorstore|pinecone|chroma|faiss|bedrock|claude -p|airflow|\bdbt\b|pyspark|sagemaker|tool_use|\bLLM\b",
}
FRONTEND_DEPS = ("react", "vue", "@angular/core", "svelte", "next", "nuxt")
# languages with no review adapter: disclosed, never silently reviewed
UNSUPPORTED = {".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++", ".ex": "Elixir", ".exs": "Elixir", ".r": "R", ".lua": "Lua",
               ".sh": "Shell", ".pl": "Perl", ".f90": "Fortran", ".cob": "COBOL", ".vb": "Visual Basic", ".m": "Objective-C or MATLAB", ".hs": "Haskell"}


def added_text(diff):
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def deps(repo):
    p = pathlib.Path(repo) / "package.json"
    try:
        d = json.loads(p.read_text())
        return {*(d.get("dependencies") or {}), *(d.get("devDependencies") or {})}
    except (OSError, ValueError):
        return set()


def detect(repo, files, diff):
    ev = {a: [] for a in FOCUS}
    added, pk = added_text(diff), deps(repo)
    for f in files:
        base = f.rsplit("/", 1)[-1]
        if UI.search(f):
            ev["Frontend"].append(f)
        if SERVER.search(f) and not UI.search(f) and not re.search(r"(?i)(^|/)(tests?|__tests__|spec)/|test_|\.test\.|\.spec\.", f):
            ev["Backend"].append(f)
        if MOBILE.search(f):
            ev["Mobile and desktop"].append(f)
        if SQL.search(f):
            ev["Data and databases"].append(f)
        if IFACE.search(f):
            ev["Integration and messaging"].append(f)
        if INFRA.search(f):
            ev["Infrastructure and delivery"].append(f)
        if base == "package.json" and any(d in pk for d in FRONTEND_DEPS):
            ev["Frontend"].append(f"{f} ({', '.join(d for d in FRONTEND_DEPS if d in pk)})")
        if base == "package.json" and ("electron" in pk or "react-native" in pk):
            ev["Mobile and desktop"].append(f"{f} (electron or react-native)")
    for area, rx in KW.items():
        hits = sorted({m.group(0).strip() for m in re.finditer(rx, added)})[:4]
        if hits:
            ev[area].append("added code mentions: " + ", ".join(hits))
    ev["Cross-cutting"] = ["always reviewed"]
    areas = [dict(area=a, focus=FOCUS[a], evidence=e[:5]) for a, e in ev.items() if e]
    un = {}
    for f in files:
        ext = pathlib.PurePosixPath(f).suffix.lower()
        if ext in UNSUPPORTED:
            un.setdefault(UNSUPPORTED[ext], []).append(f)
    return dict(areas=areas, unsupported=[dict(what=k, why=f"no review adapter ({', '.join(v[:3])}): specialist review required, nothing was assumed") for k, v in un.items()])


def render(det):
    rows = "\n".join(f"| {a['area']} | {a['focus']} | {'; '.join(a['evidence'])} |" for a in det["areas"])
    un = "\n".join(f"- **{u['what']}**: {u['why']}" for u in det["unsupported"]) or "None found in the changed files."
    return ("## Status\nDetected by the code from repository evidence (ground truth for which areas this change touches).\n\n## Review areas\n"
            "| Area | Review focus | Evidence |\n|---|---|---|\n" + rows + "\n\n## Unsupported areas (routed for specialist review)\n" + un + "\n")


def prompt_note(det):
    return ("\n\nReview areas detected by the code (focus your review on these, and ignore areas not listed):\n"
            + "\n".join(f"- {a['area']}: {a['focus']}" for a in det["areas"])
            + ("\nUnsupported here (do NOT review, say they need a specialist): " + ", ".join(u["what"] for u in det["unsupported"]) if det["unsupported"] else ""))
