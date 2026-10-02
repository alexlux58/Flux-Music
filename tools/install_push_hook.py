"""Install the ordinary-origin and gitleaks guard without overwriting hooks."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HOOK = """#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) exec python "$root/tools/pre_push.py" --hook "$@" ;;
    *) exec python3 "$root/tools/pre_push.py" --hook "$@" ;;
esac
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
    target = directory / "pre-push"
    if target.exists() and target.read_text() != HOOK:
        raise RuntimeError("Existing pre-push hook needs review; refusing to overwrite")
    target.write_text(HOOK, encoding="utf-8", newline="\n")
    target.chmod(0o755)
    print("Installed checked-origin/gitleaks pre-push hook")


if __name__ == "__main__":
    main()
