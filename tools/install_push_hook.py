"""Install the ordinary-origin and gitleaks guard without overwriting hooks."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = """#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) exec python "$root/tools/pre_push.py" --hook "$@" ;;
    *) exec python3 "$root/tools/pre_push.py" --hook "$@" ;;
esac
"""
COMMIT_HOOK = """#!/bin/sh
set -eu
exec gitleaks git --staged --redact=100 --no-banner
"""


def main():
    directory = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=ROOT,
            text=True,
        ).strip()
    )
    if not directory.is_absolute():
        directory = ROOT / directory
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in (("pre-push", HOOK), ("pre-commit", COMMIT_HOOK)):
        target = directory / name
        if target.exists() and target.read_text() != content:
            raise RuntimeError(f"Existing {name} hook needs review; refusing to overwrite")
        target.write_text(content, encoding="utf-8", newline="\n")
        target.chmod(0o755)
    print("Installed staged-gitleaks and checked-origin/gitleaks push hooks")


if __name__ == "__main__":
    main()
