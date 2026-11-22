"""The diff scanner (coder/diffscan.py): plain code that finds secrets, unsafe defaults, swallowed errors and leftovers."""
from coder import diffscan as d


def _scan(*lines, path="src/app.py", files=()):
    return d.scan([(path, i + 1, t) for i, t in enumerate(lines)], files)


def _kinds(found):
    return [(f["kind"], f["severity"]) for f in found]


def test_parse_diff_gives_added_lines_with_new_file_line_numbers_and_ignores_the_rest():
    diff = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,3 +1,4 @@\n keep\n-old\n+new1\n+new2\n keep\n"
            "@@ -10,2 +11,3 @@\n ctx\n+added\n tail\n"
            "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-bye\n"
            "diff --git a/n.py b/n.py\nnew file mode 100644\n--- /dev/null\n+++ b/n.py\n@@ -0,0 +1,2 @@\n+one\n+two\n")
    assert d.parse_diff(diff) == [("a.py", 2, "new1"), ("a.py", 3, "new2"), ("a.py", 12, "added"), ("n.py", 1, "one"), ("n.py", 2, "two")]


def test_secrets_are_found_blocked_and_masked():
    key, token = "AKIAABCDEFGHIJKLMNOP", "ghp_" + "a1B2c3D4e5" * 4
    found = _scan(f'aws = "{key}"', f"t = '{token}'", "-----BEGIN RSA PRIVATE KEY-----",
                  'api_key = "sk_live_abcdefghijklmnop1234"', 'password: "hunter2hunter2"')
    assert [f["severity"] for f in found] == ["Blocker"] * 5 and all(f["kind"] == "Secret" for f in found)
    shown = " ".join(f["text"] for f in found)
    assert key not in shown and token not in shown and "sk_live_abcdefghijklmnop1234" not in shown  # never printed in full


def test_placeholders_and_environment_lookups_are_not_secrets():
    assert _scan('api_key = os.environ["API_KEY"]', 'password = "<your password>"', 'token = "${TOKEN}"',
                 'secret = "changeme-example"', "password = get_password()", 'x = "just a string"') == []


def test_unsafe_defaults_are_flagged_as_should_fix():
    cases = ["requests.get(u, verify=False)", "subprocess.run(c, shell=True)", "eval(x)", "pickle.loads(b)",
             "yaml.load(f)", "os.chmod(p, 0o777)", "DEBUG = True", 'app.run(host="0.0.0.0")', "os.system(c)",
             "git commit --no-verify", 'allow_origins=["*"]']
    for c in cases:
        found = _scan(c)
        assert ("Unsafe default", "Should fix") in _kinds(found), c
    assert _scan("yaml.load(f, Loader=SafeLoader)") == []


def test_swallowed_and_bare_exceptions_are_flagged_but_handled_ones_are_not():
    assert ("Error handling", "Should fix") in _kinds(_scan("try:", "    x()", "except:", "    log()"))
    swallowed = _scan("try:", "    x()", "except ValueError:", "    pass")
    assert any("silently ignored" in f["why"] for f in swallowed)
    assert any("empty catch" in f["why"] for f in _scan("try { x() } catch (e) {}"))
    assert _scan("try:", "    x()", "except ValueError as e:", "    raise RuntimeError('bad') from e") == []


def test_leftovers_are_checks_and_are_ignored_in_test_files():
    found = _scan("breakpoint()", "# TODO: remove", "print(x)")
    assert [f["severity"] for f in found] == ["Check"] * 3
    assert _scan("print(x)", "breakpoint()", path="tests/test_app.py") == []
    assert _scan("print(x)", path="pkg/test_thing.py") == []


def test_a_merge_conflict_marker_is_a_blocker():
    assert _kinds(_scan("<<<<<<< HEAD")) == [("Accidental edit", "Blocker")]
    assert _kinds(_scan("=======")) == [("Accidental edit", "Blocker")]


def test_sensitive_and_dependency_files_are_flagged_by_name_alone():
    found = d.scan([], [".env", "config/prod.pem", "deploy/id_rsa", "package.json", "requirements-dev.txt", "src/app.py"])
    assert _kinds(found) == [("Secret", "Blocker")] * 3 + [("Dependency change", "Check")] * 2


def test_a_clean_diff_has_no_findings_and_removed_lines_are_never_scanned():
    assert _scan("x = 1", "def f(a):", "    return a + 1") == []
    diff = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,1 @@\n-verify=False\n-password = 'hunter2hunter2'\n+ok = 1\n"
    assert d.scan(d.parse_diff(diff), ["a.py"]) == []


def test_interface_schema_and_migration_files_are_flagged_for_a_compatibility_check():
    files = ["api/openapi.yaml", "proto/a.proto", "db/migrations/001_add.sql", "app/schemas/user.json", "schema.graphql", "src/app.py"]
    found = d.scan([], files)
    assert [f["file"] for f in found] == files[:5]
    assert all(f["kind"] == "Interface or data change" and f["severity"] == "Check" for f in found)
    assert "compatibility" in found[0]["why"]
