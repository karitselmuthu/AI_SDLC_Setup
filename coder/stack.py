"""Stack scanner for the coding agent's detect step. Plain code, no model: it finds the files that define a
project's stack and counts languages, so the model reads real files instead of guessing which exist.
scan(repo) -> dict(files={category: [relative paths]}, languages={name: file count}, unrecognised={ext: count})
"""
import fnmatch
import os
import pathlib

SKIP = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", "target", ".tox",
        ".mypy_cache", ".pytest_cache", ".idea", ".next", "vendor", ".gradle", "site-packages"}
MAX_FILES = 20000  # walk cap: a monorepo larger than this is reported as truncated, never silently cut

KINDS = {  # category -> file name patterns (matched on the base name)
    "manifest": ["pyproject.toml", "requirements*.txt", "setup.py", "setup.cfg", "Pipfile", "environment.yml",
                 "package.json", "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle*", "go.mod",
                 "Cargo.toml", "Gemfile", "composer.json", "*.csproj", "*.sln", "mix.exs", "pubspec.yaml"],
    "lockfile": ["poetry.lock", "uv.lock", "Pipfile.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "bun.lockb", "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock", "gradle.lockfile",
                 "packages.lock.json", "pubspec.lock"],
    "build": ["Makefile", "Dockerfile*", "docker-compose*.y*ml", "tox.ini", "noxfile.py", "CMakeLists.txt",
              "justfile", "Taskfile.y*ml", "Rakefile", "gradlew", "mvnw"],
    "framework config": ["tsconfig*.json", "next.config.*", "vite.config.*", "webpack.config.*", "angular.json",
                         "nuxt.config.*", "svelte.config.*", "manage.py", "pytest.ini", ".eslintrc*", "eslint.config.*",
                         ".flake8", "ruff.toml", ".editorconfig", ".prettierrc*", ".nvmrc", ".node-version",
                         ".python-version", ".tool-versions", ".ruby-version", "runtime.txt", "babel.config.*",
                         "jest.config.*", "vitest.config.*", "application.properties", "application.y*ml"],
    "ci": [".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml", ".travis.yml",
           "cloudbuild.y*ml", "buildspec.y*ml"],
}
CI_DIRS = [(".github/workflows", ("*.yml", "*.yaml")), (".circleci", ("config.yml",))]
LANGS = {".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript (React)",
         ".jsx": "JavaScript (React)", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
         ".php": "PHP", ".cs": "C#", ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".swift": "Swift",
         ".scala": "Scala", ".sh": "Shell", ".sql": "SQL", ".tf": "Terraform", ".html": "HTML", ".css": "CSS",
         ".scss": "SCSS", ".vue": "Vue", ".dart": "Dart", ".ex": "Elixir", ".r": "R", ".lua": "Lua"}
# extensions that are data, documents or assets, not code: never reported as unrecognised
IGNORE = {".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".lock", ".png", ".jpg", ".jpeg", ".gif",
          ".svg", ".ico", ".pdf", ".csv", ".xml", ".log", ".env", ".gitignore", ".gitattributes", ".woff", ".woff2",
          ".ttf", ".map", ".pyc", ".rst", ".properties", ".conf", ".cfg", ".sum", ".mod", ".bat", ".ps1", ".out"}


def _match(rel, name):
    for cat, pats in KINDS.items():
        if any(fnmatch.fnmatch(name, p) for p in pats):
            return cat
    for d, pats in CI_DIRS:
        if rel.startswith(d + "/") and any(fnmatch.fnmatch(name, p) for p in pats):
            return "ci"
    return None


def scan(repo):
    repo, files, langs, unknown, seen, truncated = pathlib.Path(repo), {}, {}, {}, 0, False
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(names):
            seen += 1
            if seen > MAX_FILES:
                truncated = True
                break
            rel = (pathlib.Path(root) / name).relative_to(repo).as_posix()
            if cat := _match(rel, name):
                files.setdefault(cat, []).append(rel)
            ext = pathlib.Path(name).suffix.lower()
            if ext in LANGS:
                langs[LANGS[ext]] = langs.get(LANGS[ext], 0) + 1
            elif ext and ext not in IGNORE and not cat:
                unknown[ext] = unknown.get(ext, 0) + 1
        if truncated:
            break
    return dict(files={k: sorted(v) for k, v in files.items()}, languages=dict(sorted(langs.items(), key=lambda kv: -kv[1])),
                unrecognised=dict(sorted(unknown.items())), truncated=truncated)


def render(found):
    """The scan as text for the prompt: what the code found, which the model must account for."""
    lines = []
    for cat in ("manifest", "lockfile", "build", "framework config", "ci"):
        lines.append(f"{cat}: " + (", ".join(found["files"].get(cat, [])) or "none found"))
    lines.append("languages by file count: " + (", ".join(f"{k} {v}" for k, v in found["languages"].items()) or "none"))
    lines.append("unrecognised file types (no known language): "
                 + (", ".join(f"{k} ({v})" for k, v in found["unrecognised"].items()) or "none"))
    if found["truncated"]:
        lines.append(f"The scan stopped after {MAX_FILES} files: the list above may be incomplete.")
    return "\n".join(lines)


def missing(found, text):
    """Detected files and unrecognised file types that the model's profile never mentions."""
    paths = [p for cat in found["files"].values() for p in cat]
    return [p for p in paths if p not in text] + [e for e in found["unrecognised"] if e not in text]
