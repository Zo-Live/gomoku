from __future__ import annotations

import curses

from .ui import run_curses_app


def main() -> int:
    return curses.wrapper(run_curses_app)
