"""Stack adapters for the coding agent. Plain code, no model.

A fixed list of "all technologies" cannot exist, so each adapter detects what the repository ACTUALLY uses (from its files)
and offers only the checks that technology has. Nothing is guessed: a technology with no adapter is reported as unsupported,
a check whose tool, dependencies or script is missing is reported as not run with the reason, and an expected kind of check
that the repository has no way to run is reported as a gap. Commands are fixed in this file (never taken from a document),
run in check mode, never install, deploy, apply, publish, push or delete, and use offline flags where the tool has them.

plan(repo) -> dict(stacks, checks, gaps, unsupported, truncated)
  stacks:   [dict(name, area, evidence=[paths or notes], conventions=[config files])]
  checks:   [dict(stack, cat, cmd, status="runnable"|"not runnable"|"manual", reason)]
  gaps:     [dict(stack, cat, reason)]          an expected kind of check the repository cannot run
  unsupported: [dict(what, reason)]             technologies found that have no adapter
runnable(plan) -> the commands that can run.   coverage(plan, extra, ran, results, approved, overridden) -> the report section.
"""
import fnmatch
import json
import os
import pathlib
import re
import shutil
import subprocess

from coder import stack

FRONT, BACK, MOBILE, DATA, DENG, INFRA, IFACE = ("Web frontend", "Backend services", "Mobile and desktop", "Data and databases",
                                                  "Data engineering and AI", "Infrastructure code", "Cross-stack interfaces")
EXPECT = {FRONT: ["format", "lint", "typecheck", "test", "build"], BACK: ["format", "lint", "build", "test"],
          MOBILE: ["build", "test", "review"], DATA: ["schema", "test"], DENG: ["test", "schema"],
          INFRA: ["format", "validate", "policy"], IFACE: ["contract"]}
LABEL = {"format": "formatting", "lint": "lint or static analysis", "typecheck": "type check", "test": "unit or component tests",
         "build": "build or compile", "review": "configuration and permission review", "schema": "schema or migration validation",
         "validate": "syntax or plan validation", "policy": "policy check", "contract": "contract or compatibility test",
         "deps": "dependency and lockfile consistency"}
# a language the scanner knows -> the start of the adapter name that covers it
LANG_ADAPTER = {"Python": "Python", "JavaScript": "JavaScript", "TypeScript": "JavaScript", "TypeScript (React)": "JavaScript",
                "JavaScript (React)": "JavaScript", "Vue": "JavaScript", "Java": "Java", "Kotlin": "Java", "Go": "Go", "Rust": "Rust",
                "Ruby": "Ruby", "PHP": "PHP", "C#": "C#", "Swift": "Swift", "Dart": "Dart", "SQL": "SQL", "Terraform": "Terraform"}
MARKUP = {"HTML", "CSS", "SCSS", "C/C++ header"}  # not stacks on their own


def C(cat, cmd, tool=None, when=(), needs=(), probe=None, why=""):
    return dict(cat=cat, cmd=cmd, tool=tool, when=when, needs=needs, probe=probe, why=why)


class Ctx:
    def __init__(self, repo):
        self.repo = pathlib.Path(repo)
        self.files, self.truncated, n = [], False, 0
        for root, dirs, names in os.walk(self.repo):
            dirs[:] = sorted(d for d in dirs if d not in stack.SKIP)
            for name in sorted(names):
                n += 1
                if n > stack.MAX_FILES:
                    self.truncated = True
                    break
                self.files.append((pathlib.Path(root) / name).relative_to(self.repo).as_posix())
            if self.truncated:
                break

    def find(self, pat):
        pats = [pat, "*/" + pat] if "/" in pat else [pat]
        return [f for f in self.files if any(fnmatch.fnmatch(f if "/" in pat else f.rsplit("/", 1)[-1], p) for p in pats)]

    def text(self, rel, limit=200_000):
        try:
            return (self.repo / rel).read_text(errors="replace")[:limit]
        except OSError:
            return ""

    def has(self, spec):
        """spec is a file glob, or 'glob::text' meaning a file matching glob that contains text. Returns evidence paths."""
        if "::" in spec:
            glob, sub = spec.split("::", 1)
            return [f for f in self.find(glob)[:20] if sub in self.text(f)]
        return self.find(spec)

    def exists(self, specs):
        """True if any spec is present: a plain name is a path (a directory counts, e.g. node_modules, which the scan skips)."""
        for sp in ([specs] if isinstance(specs, str) else specs):
            if not re.search(r"[*?\[]", sp) and (self.repo / sp).exists():
                return True
            if self.has(sp):
                return True
        return False

    def any(self, specs):
        out = []
        for s in ([specs] if isinstance(specs, str) else specs):
            out += self.has(s)
        return out


def _py(ctx):
    data = " ".join(ctx.text(f) for f in ctx.find("requirements*.txt") + ctx.find("pyproject.toml")).lower()
    deng = bool(re.search(r"pyspark|airflow|\bdbt\b|pandas|polars|langchain|torch|tensorflow|transformers|llama.index", data))
    return dict(name="Python", area=DENG if deng else BACK,
                detect=["pyproject.toml", "requirements*.txt", "setup.py", "setup.cfg", "Pipfile", "*.py"],
                conv=[".editorconfig", "ruff.toml", ".ruff.toml", ".flake8", "mypy.ini", "pytest.ini", "tox.ini", ".pylintrc", "pyproject.toml::[tool."],
                checks=[
                    C("format", "ruff format --check .", "ruff", ["ruff.toml", ".ruff.toml", "pyproject.toml::[tool.ruff"]),
                    C("format", "black --check .", "black", ["pyproject.toml::[tool.black"]),
                    C("lint", "ruff check .", "ruff", ["ruff.toml", ".ruff.toml", "pyproject.toml::[tool.ruff"]),
                    C("lint", "flake8", "flake8", [".flake8", "setup.cfg::[flake8", "tox.ini::[flake8"]),
                    C("lint", "pylint .", "pylint", [".pylintrc", "pyproject.toml::[tool.pylint"]),
                    C("typecheck", "mypy .", "mypy", ["mypy.ini", ".mypy.ini", "pyproject.toml::[tool.mypy", "setup.cfg::[mypy"]),
                    C("typecheck", "pyright", "pyright", ["pyrightconfig.json", "pyproject.toml::[tool.pyright"]),
                    C("test", "pytest -q", "pytest", ["pytest.ini", "conftest.py", "test_*.py", "tests/test_*.py", "tests/*_test.py",
                                                      "pyproject.toml::pytest", "tox.ini::pytest", "setup.cfg::pytest"]),
                    C("build", "python3 manage.py check", "python3", ["manage.py"], probe="python3 -c 'import django'",
                      why="Django is not importable here"),
                    C("schema", "python3 manage.py makemigrations --check --dry-run", "python3", ["manage.py"],
                      probe="python3 -c 'import django'", why="Django is not importable here"),
                    C("deps", "poetry check --lock", "poetry", ["poetry.lock"]),
                    C("deps", "uv lock --check --offline", "uv", ["uv.lock"])],
                lock_missing=["poetry.lock", "uv.lock", "Pipfile.lock"])


def _node(ctx):
    pj = ctx.find("package.json")
    if not [p for p in pj if "/" not in p]:
        return None
    try:
        data = json.loads(ctx.text("package.json"))
    except ValueError:
        data = {}
    scripts, deps = data.get("scripts") or {}, {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    pm = "pnpm" if ctx.find("pnpm-lock.yaml") else "yarn" if ctx.find("yarn.lock") else "npm"
    fw = [(k, n) for k, n in (("react-native", "React Native"), ("expo", "Expo"), ("electron", "Electron"),
                              ("@angular/core", "Angular"), ("next", "Next.js"), ("nuxt", "Nuxt"), ("react", "React"),
                              ("vue", "Vue"), ("svelte", "Svelte"), ("@nestjs/core", "NestJS"), ("express", "Express"),
                              ("fastify", "Fastify")) if k in deps]
    names = [n for _, n in fw]
    area = (MOBILE if {"React Native", "Expo", "Electron"} & set(names) else
            FRONT if {"Angular", "Next.js", "Nuxt", "React", "Vue", "Svelte"} & set(names) else BACK)
    needs = ["node_modules"]
    why = "dependencies are not installed (node_modules is missing) and the agent never installs"
    checks = []
    for cat, cands in (("format", ("format:check", "prettier:check", "check-format", "format-check")), ("lint", ("lint",)),
                       ("typecheck", ("typecheck", "type-check", "check-types", "tsc")), ("test", ("test",)), ("build", ("build",))):
        for n in cands:
            if n in scripts and not (n == "test" and "no test specified" in scripts[n]):
                cmd = f"{pm} test" if n == "test" else (f"{pm} run {n}" if pm != "yarn" else f"yarn {n}")
                checks.append(C(cat, cmd, pm, needs=needs, why=why))
                break
        else:
            if cat == "typecheck" and ctx.find("tsconfig*.json") and "typescript" in deps:
                checks.append(C(cat, "npx --no-install tsc --noEmit", "npx", needs=needs, why=why))
            if cat == "lint" and ctx.any(["eslint.config.*", ".eslintrc*"]) and "eslint" in deps:
                checks.append(C(cat, "npx --no-install eslint .", "npx", needs=needs, why=why))
            if cat == "format" and ctx.any([".prettierrc*", "prettier.config.*"]) and "prettier" in deps:
                checks.append(C(cat, "npx --no-install prettier --check .", "npx", needs=needs, why=why))
    lock = ctx.any(["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"])
    if lock:
        checks.append(C("deps", {"npm": "npm ls --all", "yarn": "yarn check --integrity", "pnpm": "pnpm ls"}[pm], pm,
                        needs=needs, why=why))
    evid = ["package.json"] + lock + [f"package.json lists {k}" for k, _ in fw]
    conv = ctx.any([".eslintrc*", "eslint.config.*", ".prettierrc*", "prettier.config.*", "tsconfig*.json", ".editorconfig"])
    nested = [p for p in pj if "/" in p]
    if nested:
        evid.append(f"{len(nested)} nested package.json file(s): only the root scripts are used ({', '.join(nested[:3])})")
    return dict(name="JavaScript/TypeScript (" + (", ".join(names) or pm) + ")", area=area, detect=[], evidence=evid, conv=conv,
                checks=checks, lock_missing=["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"])


def _java(ctx):
    out = []
    offline = "the Maven dependencies are not available offline"
    if ctx.find("pom.xml"):
        mvn, text = ("./mvnw" if ctx.find("mvnw") else "mvn"), ctx.text("pom.xml")
        probe = f"{mvn} -o -B -q validate"
        ck = [C("build", f"{mvn} -o -B -q test-compile", mvn, probe=probe, why=offline),
              C("test", f"{mvn} -o -B -q test", mvn, probe=probe, why=offline)]
        for plug in ("spotless", "checkstyle"):
            if plug in text:
                ck.append(C("format" if plug == "spotless" else "lint", f"{mvn} -o -B -q {plug}:check", mvn, probe=probe, why=offline))
        out.append(dict(name="Java/Kotlin (Maven" + (", Spring Boot" if "spring-boot" in text else "") + ")", area=BACK,
                        detect=["pom.xml"], conv=[".editorconfig", "checkstyle*.xml"], checks=ck))
    gr = ctx.any(["build.gradle", "build.gradle.kts"])
    if gr:
        g = "./gradlew" if ctx.find("gradlew") else "gradle"
        text = " ".join(ctx.text(f) for f in gr)
        man = ctx.find("AndroidManifest.xml")
        android = "com.android" in text or bool(man)
        ck = [C("build", f"{g} --offline assemble", g), C("test", f"{g} --offline test", g)]
        for key, task, cat in (("spotless", "spotlessCheck", "format"), ("ktlint", "ktlintCheck", "format"),
                               ("detekt", "detekt", "lint"), ("checkstyle", "checkstyleMain", "lint")):
            if key in text:
                ck.append(C(cat, f"{g} --offline {task}", g))
        if android:
            ck.append(C("lint", f"{g} --offline lintDebug", g))
            ck.append(C("review", None, why="permissions, exported components and configuration need a person: " + (", ".join(man[:3]) or "no AndroidManifest.xml found")))
        out.append(dict(name="Java/Kotlin (Gradle" + (", Android" if android else "") + ")", area=MOBILE if android else BACK,
                        detect=["build.gradle", "build.gradle.kts"], conv=[".editorconfig", "detekt.yml"], checks=ck))
    return out


def _dotnet(ctx):
    n = dict(needs=["*obj/project.assets.json"], why="NuGet packages are not restored and the agent never restores")
    return dict(name="C# (.NET)", area=BACK, detect=["*.sln", "*.csproj"], conv=[".editorconfig", "Directory.Build.props", "*.ruleset"],
                checks=[C("format", "dotnet format --verify-no-changes --no-restore", "dotnet", [".editorconfig"], **n),
                        C("build", "dotnet build --no-restore", "dotnet", **n), C("test", "dotnet test --no-restore", "dotnet", **n)])


def _go(ctx):
    n = dict(probe="go list ./...", why="the Go modules are not available offline")
    return dict(name="Go", area=BACK, detect=["go.mod"], conv=[".golangci.y*ml", ".editorconfig"], checks=[
        C("build", "go build ./...", "go", **n), C("lint", "go vet ./...", "go", **n), C("lint", "golangci-lint run", "golangci-lint", [".golangci.y*ml"]),
        C("test", "go test ./...", "go", **n), C("deps", "go mod verify", "go", ["go.sum"])], lock_missing=["go.sum"])


def _rust(ctx):
    return dict(name="Rust", area=BACK, detect=["Cargo.toml"], conv=["rustfmt.toml", ".rustfmt.toml", "clippy.toml"], checks=[
        C("format", "cargo fmt --check", "cargo"), C("lint", "cargo clippy --offline", "cargo"),
        C("build", "cargo build --offline", "cargo"), C("test", "cargo test --offline", "cargo"),
        C("deps", "cargo metadata --offline --locked --format-version 1", "cargo", ["Cargo.lock"])], lock_missing=["Cargo.lock"])


def _php(ctx):
    return dict(name="PHP", area=BACK, detect=["composer.json"], conv=[".editorconfig", "phpcs.xml*", "phpstan.neon*", ".php-cs-fixer*"], checks=[
        C("format", "vendor/bin/php-cs-fixer fix --dry-run", "vendor/bin/php-cs-fixer", [".php-cs-fixer*"]),
        C("lint", "vendor/bin/phpstan analyse", "vendor/bin/phpstan", ["phpstan.neon*"]),
        C("test", "vendor/bin/phpunit", "vendor/bin/phpunit", ["phpunit.xml*"]),
        C("deps", "composer validate --no-check-publish", "composer", ["composer.lock"])], lock_missing=["composer.lock"])


def _ruby(ctx):
    return dict(name="Ruby", area=BACK, detect=["Gemfile"], conv=[".rubocop.yml", ".editorconfig"], checks=[
        C("lint", "bundle exec rubocop", "bundle", [".rubocop.yml"]), C("test", "bundle exec rspec", "bundle", [".rspec", "spec/*_spec.rb"]),
        C("deps", "bundle check", "bundle", ["Gemfile.lock"])], lock_missing=["Gemfile.lock"])


def _swift(ctx):
    plist = (ctx.find("Info.plist") + ctx.find("*.entitlements"))[:3]
    ck = [C("lint", "swiftlint lint --strict", "swiftlint", [".swiftlint.yml"]), C("build", "swift build", "swift", ["Package.swift"]),
          C("test", "swift test", "swift", ["Package.swift"]),
          C("review", None, why="Info.plist entitlements and permissions need a person: " + (", ".join(plist) or "none found"))]
    if ctx.find("*.xcodeproj/project.pbxproj") and not ctx.find("Package.swift"):
        ck.append(C("build", None, why="an Xcode project without a Swift package needs a scheme and a simulator, which the agent does not choose"))
    return dict(name="Swift", area=MOBILE, detect=["Package.swift", "*.xcodeproj/project.pbxproj"], conv=[".swiftlint.yml", ".swiftformat"], checks=ck)


def _dart(ctx):
    fl = "flutter" in ctx.text("pubspec.yaml")
    t = "flutter" if fl else "dart"
    perms = (ctx.find("AndroidManifest.xml") + ctx.find("Info.plist"))[:3]
    return dict(name="Dart/Flutter" if fl else "Dart", area=MOBILE if fl else BACK, detect=["pubspec.yaml"], conv=["analysis_options.yaml"], checks=[
        C("format", "dart format --output=none --set-exit-if-changed .", "dart"),
        C("lint", "flutter analyze --no-pub" if fl else "dart analyze", t), C("test", "flutter test --no-pub" if fl else "dart test", t),
        C("review", None, why="platform permissions and configuration need a person: " + (", ".join(perms) or "none found"))])


def _sql(ctx):
    return dict(name="SQL", area=DATA, detect=["*.sql"], conv=[".sqlfluff"], checks=[
        C("lint", "sqlfluff lint .", "sqlfluff", [".sqlfluff"]),
        C("schema", None, when=["migrations/*", "db/migrate/*", "*/migrations/*.sql", "V*__*.sql", "alembic.ini", "prisma/schema.prisma", "dbt_project.yml"],
          why="migrations or models exist, but validating them needs a database or warehouse the agent does not start or contact")])


def _terraform(ctx):
    return dict(name="Terraform", area=INFRA, detect=["*.tf"], conv=[".tflint.hcl", ".terraform-version"], checks=[
        C("format", "terraform fmt -check -recursive", "terraform"),
        C("validate", "terraform validate", "terraform", needs=[".terraform/*", "*/.terraform/*"],
          why="terraform init has not been run and the agent never initialises (it downloads providers)"),
        C("policy", "tflint", "tflint", [".tflint.hcl"]), C("policy", "checkov -d . --quiet", "checkov", [".checkov.y*ml"])])


def _helm(ctx):
    charts = ctx.find("Chart.yaml")
    d = os.path.dirname(charts[0]) or "." if charts else "."
    return dict(name="Helm", area=INFRA, detect=["Chart.yaml"], conv=["values.yaml"], checks=[
        C("validate", f"helm lint {d}", "helm"), C("validate", f"helm template {d}", "helm"),
        C("policy", None, when=["conftest.y*ml", "policy/*.rego"], why="policy files exist but no policy runner command is chosen automatically")])


def _cdk(ctx):
    return dict(name="AWS CDK", area=INFRA, detect=["cdk.json"], conv=["cdk.json"], checks=[
        C("validate", None, why="cdk synth may call AWS for context lookups, so the agent does not run it; the build and tests run through the Node adapter"),
        C("policy", None, why="no policy runner is configured")])


def _pulumi(ctx):
    return dict(name="Pulumi", area=INFRA, detect=["Pulumi.y*ml"], conv=["Pulumi.y*ml"], checks=[
        C("validate", None, why="pulumi preview needs a backend and credentials, which the agent does not use"),
        C("policy", None, why="no policy runner is configured")])


def _cfn(ctx):
    ts = [f for f in ctx.files if f.endswith((".yml", ".yaml", ".json", ".template")) and "AWSTemplateFormatVersion" in ctx.text(f, 4000)][:20]
    if not ts:
        return None
    return dict(name="CloudFormation", area=INFRA, detect=[], evidence=ts, conv=[".cfnlintrc*"],
                checks=[C("validate", "cfn-lint " + " ".join(ts), "cfn-lint"), C("policy", "cfn-guard validate --rules rules --data " + ts[0], "cfn-guard", ["rules/*.guard"]),
                        C("format", None, why="CloudFormation has no standard formatter")])


def _k8s(ctx):
    def manifest(f):
        t = ctx.text(f, 4000)
        return (f.endswith((".yml", ".yaml")) and not f.startswith((".github/", ".circleci/")) and re.search(r"(?m)^apiVersion:", t)
                and re.search(r"(?m)^kind:\s*(Deployment|Service|StatefulSet|DaemonSet|Ingress|ConfigMap|CronJob|Job|Pod)\b", t))
    ys = [f for f in ctx.files if manifest(f)][:20]
    if not ys:
        return None
    return dict(name="Kubernetes manifests", area=INFRA, detect=[], evidence=ys, conv=[],
                checks=[C("validate", "kubeconform -summary -ignore-missing-schemas " + " ".join(ys), "kubeconform"),
                        C("policy", None, when=["conftest.y*ml", "policy/*.rego"], why="policy files exist but no policy runner command is chosen automatically"),
                        C("format", None, why="no standard formatter is configured for these manifests")])


def _datastores(ctx):
    src = ctx.any(["docker-compose*.y*ml", "compose*.y*ml", "requirements*.txt", "pyproject.toml", "package.json", "pom.xml", "go.mod", "Gemfile", "composer.json", "*.csproj"])
    blob = " ".join(ctx.text(f, 50000) for f in src).lower()
    kinds = [n for pat, n in ((r"postgres|psycopg", "PostgreSQL"), (r"mysql|mariadb", "MySQL"), (r"mongo", "MongoDB"),
                              (r"\bredis\b", "Redis"), (r"oracle|ojdbc|cx_oracle|oracledb", "Oracle"), (r"mssql|sqlserver|sql server|pyodbc", "SQL Server")) if re.search(pat, blob)]
    if not kinds:
        return None
    return dict(name="Datastores (" + ", ".join(kinds) + ")", area=DATA, detect=[], evidence=src[:6], conv=[],
                checks=[C("schema", None, why="query, compatibility and migration tests need a running database, which the agent does not start or contact"),
                        C("test", None, why="integration tests against these datastores are not run; only database-free unit tests can run")])


def _iface(ctx):
    ev = ctx.any(["openapi*.y*ml", "openapi*.json", "swagger*.y*ml", "swagger*.json", "*.graphql", "*.gql", "*.proto", "asyncapi*.y*ml", "schemas/*.json"])
    if not ev:
        return None
    ck = [C("contract", "buf lint", "buf", ["buf.yaml"])]
    for f in ctx.any(["openapi*.y*ml", "openapi*.json"])[:3]:
        ck.append(C("contract", f"spectral lint {f}", "spectral", [".spectral.y*ml", ".spectral.json"]))
    ck.append(C("contract", None, why="no automated compatibility check is configured; consumers of these interfaces need contract tests, and step 7 flags changes to these files"))
    return dict(name="Interfaces and shared schemas", area=IFACE, detect=[], evidence=ev[:8], conv=[".spectral.y*ml", "buf.yaml"], checks=ck)


ADAPTERS = [_py, _node, _java, _dotnet, _go, _rust, _php, _ruby, _swift, _dart, _sql, _terraform, _helm, _cdk, _pulumi,
            _cfn, _k8s, _datastores, _iface]


def _tool_ok(repo, tool):
    if not tool:
        return True
    if "/" in tool:
        return (pathlib.Path(repo) / tool).is_file()
    return shutil.which(tool) is not None


def _probe_ok(repo, probe):
    try:
        return subprocess.run(probe, shell=True, cwd=str(repo), capture_output=True, timeout=90, stdin=subprocess.DEVNULL).returncode == 0
    except subprocess.TimeoutExpired:
        return False


MODULE_FILES = ["package.json", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml", "pyproject.toml", "setup.py",
                "*.csproj", "composer.json", "Gemfile", "pubspec.yaml", "Package.swift"]


def modules(repo):
    """Directories that hold a build manifest ('.' is the repository root): the repository's modules, from files only."""
    ctx = Ctx(repo)
    return sorted({(f.rsplit("/", 1)[0] if "/" in f else ".") for pat in MODULE_FILES for f in ctx.find(pat)})


def touched(mods, files):
    """The modules a set of changed files falls in (the deepest module wins; files in no module sit in the root)."""
    out = set()
    for f in files:
        best = max((m for m in mods if m != "." and f.startswith(m + "/")), key=len, default=None)
        if best:
            out.add(best)
        elif "." in mods:
            out.add(".")
    return sorted(out)


def plan(repo):
    ctx, stacks, checks, gaps, seen, specs = Ctx(repo), [], [], [], set(), []
    for fn in ADAPTERS:
        r = fn(ctx)
        specs += r if isinstance(r, list) else [r] if r else []
    for sp in specs:
        evid = sp.get("evidence") or ctx.any(sp["detect"])
        if not evid:
            continue
        name = sp["name"]
        stacks.append(dict(name=name, area=sp["area"], evidence=list(dict.fromkeys(evid))[:8],
                           conventions=list(dict.fromkeys(ctx.any(sp["conv"])))[:8]))
        got = set()
        for ck in sp["checks"]:
            if ck["when"] and not ctx.any(ck["when"]):
                continue
            row = dict(stack=name, cat=ck["cat"], cmd=ck["cmd"], status="runnable", reason="")
            if ck["cmd"] is None:
                row.update(status="manual", reason=ck["why"])
            elif ck["cmd"] in seen:
                continue
            elif not _tool_ok(repo, ck["tool"]):
                row.update(status="not runnable", reason=f"`{ck['tool']}` is not installed here")
            elif ck["needs"] and not ctx.exists(ck["needs"]):
                row.update(status="not runnable", reason=ck["why"])
            elif ck["probe"] and not _probe_ok(repo, ck["probe"]):
                row.update(status="not runnable", reason=ck["why"] or f"`{ck['probe']}` failed")
            if ck["cmd"]:
                seen.add(ck["cmd"])
            got.add(ck["cat"])
            checks.append(row)
        if sp.get("lock_missing") and not ctx.any(sp["lock_missing"]) and "deps" not in got:
            gaps.append(dict(stack=name, cat="deps", reason="no lockfile was found, so lockfile consistency cannot be checked"))
        for cat in EXPECT[sp["area"]]:
            if cat not in got:
                gaps.append(dict(stack=name, cat=cat, reason=f"no {LABEL[cat]} is configured or detectable for this stack"))
    names = [s["name"] for s in stacks]
    langs = stack.scan(repo)
    unsupported = []
    for lang, cnt in langs["languages"].items():
        want = LANG_ADAPTER.get(lang)
        if lang in MARKUP:
            continue
        if want is None:
            unsupported.append(dict(what=f"{lang} ({cnt} files)", reason="no adapter for this language: no conventions or checks were selected and nothing is guessed"))
        elif not any(n.startswith(want) for n in names):
            unsupported.append(dict(what=f"{lang} ({cnt} files)", reason=f"source files found but no {want} manifest or build file, so no checks can be chosen"))
    handled = {os.path.splitext(e)[1].lower() for st in stacks for e in st["evidence"]}  # e.g. .proto, owned by the interfaces adapter
    for ext, cnt in langs["unrecognised"].items():
        if ext in handled:
            continue
        unsupported.append(dict(what=f"{ext} files ({cnt})", reason="unrecognised file type: no adapter, no checks selected"))
    return dict(stacks=stacks, checks=checks, gaps=gaps, unsupported=unsupported, truncated=ctx.truncated or langs["truncated"],
                modules=sorted({(f.rsplit("/", 1)[0] if "/" in f else ".") for pat in MODULE_FILES for f in ctx.find(pat)}))


def runnable(p):
    return [c["cmd"] for c in p["checks"] if c["status"] == "runnable"]


def prompt_note(p):
    """What the model is told about the stack in the implement and test steps, from evidence only."""
    if not p["stacks"]:
        return "\n\nNo supported stack was detected in the repository: follow the repository's own files and report what you could not infer."
    lines = [f"- {s['name']} ({s['area']}); evidence: {', '.join(s['evidence'][:4])}; the repository's own convention files: "
             f"{', '.join(s['conventions']) or 'none found'}" for s in p["stacks"]]
    un = [u["what"] for u in p["unsupported"]]
    return ("\n\nDetected stack (by the code, from the repository's files). Follow these stacks' existing conventions as the repository "
            "shows them, and do not assume anything about a technology that is not listed:\n" + "\n".join(lines)
            + ("\nNo adapter exists for: " + ", ".join(un) + ". Say so instead of guessing about these." if un else ""))


def render(p):
    """The adapter findings as text for the detect step's prompt: ground truth the model must account for."""
    if not p["stacks"] and not p["unsupported"]:
        return "stack adapters: no supported technology detected"
    lines = ["stack adapters (code-detected): " + ("; ".join(f"{s['name']} [{s['area']}]" for s in p["stacks"]) or "none")]
    lines += [f"unsupported by any adapter (list each under Unsupported or uncertain components): {u['what']}: {u['reason']}" for u in p["unsupported"]]
    return "\n".join(lines)


def _rows(n, data):
    return "\n".join("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in r) + " |" for r in data) or "| none |" + " |" * (n - 1)


def _result(r):
    return f"Not run: environment failure: {r['env']}" if r.get("env") else f"{'PASS' if r['rc'] == 0 else 'FAIL'} (exit {r['rc']})"


def outcomes(p, extra, ran, results, approved=True, overridden=False):
    """One outcome string per check of the plan. PASS or FAIL only if the check ran and its result is in `results`."""
    got = {r["cmd"]: r for r in (results or [])}
    out = []
    for c in p["checks"]:
        if c["status"] == "manual":
            out.append("Not run: needs a person. " + c["reason"])
        elif c["status"] == "not runnable":
            out.append("Not run: " + c["reason"])
        elif overridden and c["cmd"] not in extra:
            out.append("Not run: replaced by the --check commands given")
        elif not ran or c["cmd"] not in got:
            out.append("Not run: " + ("the list was not approved" if not approved else "no check run was recorded"))
        else:
            r = got[c["cmd"]]
            out.append(_result(r))
    return out


def summary(p, extra, ran, results, approved=True, overridden=False, files=()):
    """One sentence for the verdict: how much of the selected coverage did not run, and the gaps."""
    o = outcomes(p, extra, ran, results, approved, overridden)
    skipped, gaps, uns = sum(not x.startswith(("PASS", "FAIL")) for x in o), len(p["gaps"]), len(p["unsupported"])
    if not (skipped or gaps or uns):
        return ""
    return (f" Coverage is not complete: {skipped} selected check(s) did not run, {gaps} gap(s), {uns} unsupported technolog"
            f"{'y' if uns == 1 else 'ies'} (see Stack coverage).")


def coverage(p, extra, ran, results, approved=True, overridden=False, files=()):
    """The 'Stack coverage' section of the test report."""
    got = {r["cmd"]: r for r in (results or [])}
    o = outcomes(p, extra, ran, results, approved, overridden)
    sel = p["checks"]
    n_run = sum(x.startswith(("PASS", "FAIL")) for x in o)
    parts = ["## Stack coverage (from the code; a check is only PASS or FAIL if it was run)",
             "### Detected stack\n| Stack | Area | Evidence | Convention files |\n|---|---|---|---|\n"
             + _rows(4, [(s["name"], s["area"], ", ".join(s["evidence"]), ", ".join(s["conventions"]) or "none found") for s in p["stacks"]]),
             f"### Checks selected ({len(sel)}), run ({n_run}), not run ({len(sel) - n_run})\n| Stack | Kind | Command | Outcome |\n|---|---|---|---|\n"
             + _rows(4, [(c["stack"], LABEL[c["cat"]], f"`{c['cmd']}`" if c["cmd"] else "(manual)", x) for c, x in zip(sel, o)]),
             "### Gaps (an expected kind of check the repository has no way to run)\n| Stack | Kind | Reason |\n|---|---|---|\n"
             + _rows(3, [(g["stack"], LABEL[g["cat"]], g["reason"]) for g in p["gaps"]]),
             "### Unsupported technologies\n" + ("\n".join(f"- {u['what']}: {u['reason']}" for u in p["unsupported"]) or "None.")]
    known = {c["cmd"] for c in sel}
    others = [c for c in (extra or []) if c not in known]
    if others:
        parts.append("### Other checks (from the stack profile or --check)\n| Command | Outcome |\n|---|---|\n" + _rows(2, [
            (f"`{c}`", _result(got[c]) if ran and c in got else "Not run") for c in others]))
    mods = p.get("modules", [])
    if len(mods) > 1:
        hit = touched(mods, files)
        rest = [m for m in mods if m not in hit]
        parts.append("### Modules\nThe repository has " + str(len(mods)) + " modules (directories with a build manifest): " + ", ".join(f"`{m}`" for m in mods)
                     + ".\nThe change touches: " + (", ".join(f"`{m}`" for m in hit) or "none") + ".\nNot touched: " + (", ".join(f"`{m}`" for m in rest) or "none")
                     + ". The checks above run from the repository root. Which modules depend on the touched ones is **not computed by the code**: "
                       "a dependent module's build and tests were not run unless a check listed above covers them.")
    if p["truncated"]:
        parts.append("The file scan stopped at its cap, so detection may be incomplete.")
    return "\n\n".join(parts)
