"""Application entrypoint."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.app import create_app
from src.utils.logging import get_logger


def _ensure_stdio() -> None:
    """PyInstaller windowed / pythonw leave stdout/stderr as None."""
    import io

    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()


def _refresh_windows_path() -> None:
    """Use installed user tools even when the parent process has a stale PATH."""
    if sys.platform != "win32":
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            user_path, _ = winreg.QueryValueEx(key, "Path")
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + os.path.expandvars(user_path)
    except OSError:
        pass  # Keep the inherited process PATH; diagnostics reports missing tools.


def main(argv: list[str] | None = None) -> int:
    _ensure_stdio()
    _refresh_windows_path()
    parser = argparse.ArgumentParser(description="Music Library")
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Run the any-device web UI without the desktop window",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Component root (defaults to services/music-library)",
    )
    parser.add_argument("--verify-audio", type=Path, help="Read-only packaged audio self-check")
    parser.add_argument("--report", type=Path, help="Write self-check JSON; no catalog is opened")
    args = parser.parse_args(argv)
    if args.verify_audio:
        import json

        from src.config import project_root
        from src.services.metadata import MetadataService
        from src.services.tempo import TempoAnalyzer, bpm_category

        if not args.report:
            parser.error("--verify-audio requires --report")
        bpm = TempoAnalyzer().estimate(args.verify_audio)
        metadata = MetadataService().read(args.verify_audio)
        args.report.write_text(
            json.dumps(
                {
                    "bpm": bpm,
                    "category": bpm_category(bpm),
                    "root": str(project_root()),
                    "title": metadata.title,
                }
            ),
            encoding="utf-8",
        )
        return 0

    ctx = create_app(root=args.root)
    logger = get_logger("main")

    from src.web.api import start_web_server

    start_web_server(ctx)
    logger.info(
        "Web UI on http://%s:%s",
        ctx.config.ui.web_host,
        ctx.config.ui.web_port,
    )

    if args.web_only:
        try:
            import time

            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    from PySide6.QtWidgets import QApplication

    from src.ui.main_window import MainWindow

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName(ctx.config.app.name)
    window = MainWindow(ctx)
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
