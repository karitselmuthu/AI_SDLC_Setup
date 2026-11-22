"""Static scan of a change's diff for the review step. Plain code, no model, so a review can never miss a secret
because a model was in a hurry. Only ADDED lines are scanned. Secrets are masked in everything it returns.
parse_diff(text) -> [(path, new_line_number, text)]    scan(added, files) -> [dict(kind, severity, file, line, text, why)]
Severities: Blocker (must be resolved before a human reviews), Should fix, Check (look at it, may be intended).
"""
import fnmatch
import re

SECRETS = [
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    ("JSON web token", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
]
CREDENTIAL = re.compile(r"""(?i)\b(api[_-]?key|secret|token|passwd|password|private[_-]?key)\w*\s*[:=]\s*['"]([^'"\s]{8,})['"]""")
PLACEHOLDER = re.compile(r"(?i)example|changeme|placeholder|your[_-]|<|\$\{|xxx|\*\*\*|dummy|fake|test")
SENSITIVE_FILES = [".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*.p12", "*.pfx", "*.keystore",
                   "credentials*", "*.kdbx", ".npmrc", ".pypirc"]
DEPENDENCY_FILES = ["package.json", "requirements*.txt", "pyproject.toml", "Pipfile", "go.mod", "Cargo.toml", "pom.xml",
                    "build.gradle*", "Gemfile", "composer.json", "*.lock", "package-lock.json", "yarn.lock", "go.sum"]
INTERFACE_FILES = ["openapi*.y*ml", "openapi*.json", "swagger*.y*ml", "swagger*.json", "*.graphql", "*.gql", "*.proto",
                   "asyncapi*.y*ml", "*.avsc", "*.sql", "*.prisma", "alembic.ini", "schema.rb"]
INTERFACE_DIRS = ("migrations/", "db/migrate/", "schemas/", "/migrations/", "/schemas/")
UNSAFE = [
    ("TLS verification disabled", r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true"),
    ("shell=True (command injection risk)", r"shell\s*=\s*True"),
    ("eval or exec", r"\b(eval|exec)\s*\("),
    ("unsafe deserialisation", r"\bpickle\.loads?\(|\byaml\.load\((?![^)]*Loader=)"),
    ("world-writable permissions", r"chmod\s+(-R\s+)?0?777|0o777"),
    ("debug mode switched on", r"\bDEBUG\s*=\s*True\b|\bdebug\s*=\s*True\b"),
    ("listens on all interfaces", r"\b0\.0\.0\.0\b"),
    ("CORS allows any origin", r"""allow_origins\s*=\s*\[\s*['"]\*['"]|Access-Control-Allow-Origin['"]?\s*[:,]\s*['"]\*"""),
    ("os.system call", r"\bos\.system\("),
    ("verification or safety bypass flag", r"--no-verify|--insecure|--no-check-certificate"),
]
LEFTOVERS = [
    ("debugger left in", r"\bdebugger\b|\bbreakpoint\(\)|\bpdb\.set_trace|^\s*import pdb"),
    ("TODO or FIXME added", r"\b(TODO|FIXME|XXX)\b"),
    ("output statement added", r"\bprint\(|console\.log\("),
]
CONFLICT = re.compile(r"^(<<<<<<< |=======$|>>>>>>> )")
BARE_EXCEPT = re.compile(r"^\s*except\s*:")
EXCEPT_LINE = re.compile(r"^\s*except\b[^:]*:\s*$")
SWALLOW = re.compile(r"^\s*(pass|\.\.\.)\s*(#.*)?$")
EMPTY_CATCH = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")


def parse_diff(text):
    """Added lines of a unified diff as (path, line number in the new file, text)."""
    out, path, n = [], None, 0
    for line in text.splitlines():
        if line.startswith("+++ "):
            path = None if line == "+++ /dev/null" else line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            n = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            out.append((path, n, line[1:]))
            n += 1
        elif line.startswith(" ") and path:
            n += 1
    return out


def mask(text):
    """Never print a secret in full: keep a few characters so a human can find it."""
    return re.sub(r"[A-Za-z0-9/+=_-]{12,}", lambda m: m.group(0)[:4] + "…" + f"({len(m.group(0))} chars)", text.strip())[:120]


def _hit(kind, severity, file, line, text, why):
    return dict(kind=kind, severity=severity, file=file, line=line, text=mask(text), why=why)


def scan(added, files=()):
    """Findings for the added lines and the changed file names. `files` are all changed paths, for name checks."""
    out = []
    for i, (f, n, t) in enumerate(added):
        for name, rx in SECRETS:
            if re.search(rx, t):
                out.append(_hit("Secret", "Blocker", f, n, t, f"Looks like a {name}. Remove it, rotate it, and load it from the environment."))
        if (m := CREDENTIAL.search(t)) and not PLACEHOLDER.search(m.group(2)):
            out.append(_hit("Secret", "Blocker", f, n, t, "A credential-like value is written into the code. Load it from the environment or a secret store."))
        if CONFLICT.match(t):
            out.append(_hit("Accidental edit", "Blocker", f, n, t, "A merge conflict marker was committed to the file."))
        for name, rx in UNSAFE:
            if re.search(rx, t):
                out.append(_hit("Unsafe default", "Should fix", f, n, t, name + "."))
        for name, rx in LEFTOVERS:
            if re.search(rx, t) and not f.startswith(("tests/", "test/")) and "/test_" not in "/" + f:
                out.append(_hit("Leftover", "Check", f, n, t, name + ". Confirm it is intended."))
        if BARE_EXCEPT.match(t):
            out.append(_hit("Error handling", "Should fix", f, n, t, "A bare except catches everything, including exit signals."))
        if EMPTY_CATCH.search(t):
            out.append(_hit("Error handling", "Should fix", f, n, t, "An empty catch block swallows the error."))
        if EXCEPT_LINE.match(t) and i + 1 < len(added) and added[i + 1][0] == f and SWALLOW.match(added[i + 1][2]):
            out.append(_hit("Error handling", "Should fix", f, n, t, "The error is caught and silently ignored."))
    for f in files:
        base = f.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatch(base, p) for p in SENSITIVE_FILES):
            out.append(_hit("Secret", "Blocker", f, 0, f, "A file that normally holds secrets or keys is part of the change."))
        elif any(fnmatch.fnmatch(base, p) for p in INTERFACE_FILES) or any(d in "/" + f for d in INTERFACE_DIRS):
            out.append(_hit("Interface or data change", "Check", f, 0, f,
                            "An interface, schema or migration file changed. Confirm compatibility with consumers and existing data, and that a compatibility test covers it."))
        elif any(fnmatch.fnmatch(base, p) for p in DEPENDENCY_FILES):
            out.append(_hit("Dependency change", "Check", f, 0, f, "A dependency or lock file changed. Confirm the plan allows it."))
    return out
