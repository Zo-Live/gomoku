from __future__ import annotations

import curses
import locale
import time
import textwrap
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .engine import InvalidMoveError, MatchEngine
from .exporter import export_games
from .models import GameConfig, GameResult, GameState, PlayerType, Stone
from .persistence import MatchMetadata, new_match_metadata, save_finished_game
from .players import NullPredictionProvider, PlayerContext, PlayerController, PredictionProvider, controller_for

locale.setlocale(locale.LC_ALL, "")

MIN_HEIGHT = 28
MIN_WIDTH = 92
SIZE_OPTIONS = [9, 11, 13, 15, 17, 19]
MAX_ROUND_DIGITS = len(str((max(SIZE_OPTIONS) * max(SIZE_OPTIONS)) // 2))

BLOCK = "█"
SHADOW = "▓"

LOGO_GLYPHS = {
    "G": ["011110", "100000", "100111", "100001", "011110"],
    "O": ["011110", "100001", "100001", "100001", "011110"],
    "M": ["100001", "110011", "101101", "100001", "100001"],
    "K": ["100010", "100100", "111000", "100100", "100010"],
    "U": ["100001", "100001", "100001", "100001", "011110"],
}

DIGIT_GLYPHS = {
    "0": ["01110", "10001", "10001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00010", "00100", "11111"],
    "3": ["11110", "00001", "00110", "00001", "11110"],
    "4": ["00010", "00110", "01010", "11111", "00010"],
    "5": ["11111", "10000", "11110", "00001", "11110"],
    "6": ["01110", "10000", "11110", "10001", "01110"],
    "7": ["11111", "00010", "00100", "01000", "01000"],
    "8": ["01110", "10001", "01110", "10001", "01110"],
    "9": ["01110", "10001", "01111", "00001", "01110"],
    ".": ["00000", "00000", "00000", "00110", "00110"],
    "%": ["11001", "11010", "00100", "01011", "10011"],
}


@dataclass(slots=True)
class Rect:
    y: int
    x: int
    h: int
    w: int

    def contains(self, y: int, x: int) -> bool:
        return self.y <= y < self.y + self.h and self.x <= x < self.x + self.w

    @property
    def inner_y(self) -> int:
        return self.y + 1

    @property
    def inner_x(self) -> int:
        return self.x + 1


@dataclass(slots=True)
class BoardMetrics:
    grid_top: int
    grid_left: int
    cell_width: int
    row_step: int
    size: int
    label_width: int
    board_width: int
    board_height: int


@dataclass(slots=True)
class MenuState:
    p1_type: PlayerType = PlayerType.HUMAN
    size_index: int = SIZE_OPTIONS.index(15)
    message: str = "Mouse: click boxes. Keyboard: P toggle P1, S size, Enter start."

    @property
    def board_size(self) -> int:
        return SIZE_OPTIONS[self.size_index]

    def cycle_p1(self) -> None:
        self.p1_type = PlayerType.BASELINE if self.p1_type is PlayerType.HUMAN else PlayerType.HUMAN

    def cycle_size(self) -> None:
        self.size_index = (self.size_index + 1) % len(SIZE_OPTIONS)


@dataclass(slots=True)
class GameSession:
    config: GameConfig
    engine: MatchEngine
    state: GameState
    metadata: MatchMetadata
    controllers: dict[Stone, PlayerController | None]
    predictor: PredictionProvider = field(default_factory=NullPredictionProvider)
    selected: tuple[int, int] = (0, 0)
    message: str = "Arrow keys move. Enter confirms. Mouse click selects, click again to place."
    saved_path: str | None = None

    def current_controller(self) -> PlayerController | None:
        return self.controllers[self.state.current_turn]


class TerminalApp:
    def __init__(self, stdscr: Any) -> None:
        self.stdscr = stdscr
        self.menu = MenuState()
        self.view = "menu"
        self.session: GameSession | None = None
        self.running = True
        self.hotspots: dict[str, Rect] = {}
        self.board_metrics: BoardMetrics | None = None
        self._init_curses()

    def _init_curses(self) -> None:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.stdscr.timeout(100)
        curses.mousemask(curses.BUTTON1_RELEASED)
        curses.mouseinterval(0)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, -1)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)

    def run(self) -> int:
        while self.running:
            self.render()
            if self._has_minimum_space() and self.view == "game" and self.session and not self.session.state.is_finished:
                controller = self.session.current_controller()
                if controller is not None:
                    self._step_ai(controller)
                    continue
            key = self.stdscr.getch()
            if key == -1:
                continue
            if key == curses.KEY_RESIZE:
                continue
            if self.view == "menu":
                self.handle_menu_input(key)
            else:
                self.handle_game_input(key)
        return 0

    def render(self) -> None:
        self.stdscr.erase()
        self.hotspots = {}
        self.board_metrics = None
        height, width = self.stdscr.getmaxyx()
        if height < MIN_HEIGHT or width < MIN_WIDTH:
            self._render_size_warning(height, width)
        elif self.view == "menu":
            self._render_menu(height, width)
        else:
            self._render_game(height, width)
        self.stdscr.noutrefresh()
        curses.doupdate()

    def _render_size_warning(self, height: int, width: int) -> None:
        lines = [
            "Terminal too small for gomoku UI.",
            f"Need at least {MIN_WIDTH}x{MIN_HEIGHT}, current {width}x{height}.",
            "Resize the terminal, or press Q to quit.",
        ]
        top = max(1, height // 2 - len(lines))
        for index, line in enumerate(lines):
            self._safe_addstr(top + index, max(0, (width - len(line)) // 2), line)

    def _has_minimum_space(self) -> bool:
        height, width = self.stdscr.getmaxyx()
        return height >= MIN_HEIGHT and width >= MIN_WIDTH

    def _render_menu(self, height: int, width: int) -> None:
        left_w = max(48, width - 34)
        right_w = width - left_w - 4
        logo_box = Rect(2, 3, height - 11, left_w - 4)
        p1_box = Rect(height - 8, 3, 5, (left_w - 6) // 2)
        p2_box = Rect(height - 8, 4 + (left_w - 6) // 2, 5, (left_w - 6) // 2)
        start_box = Rect(2, left_w + 1, 5, right_w)
        size_box = Rect(9, left_w + 1, 5, right_w)
        export_box = Rect(height - 10, left_w + 1, 5, right_w)
        quit_box = Rect(height - 4, left_w + 1, 4, right_w)

        self._draw_box(logo_box)
        self._draw_box(p1_box, "P1")
        self._draw_box(p2_box, "P2")
        self._draw_box(start_box, "Start")
        self._draw_box(size_box, "Size")
        self._draw_box(export_box, "Export")
        self._draw_box(quit_box, "Quit")

        self.hotspots = {
            "p1": p1_box,
            "start": start_box,
            "size": size_box,
            "export": export_box,
            "quit": quit_box,
        }

        self._draw_logo(logo_box)
        self._center_text(p1_box, self.menu.p1_type.value.title())
        self._center_text(p2_box, "Baseline")
        self._center_text(start_box, "Play")
        self._center_text(size_box, f"{self.menu.board_size}x{self.menu.board_size}")
        self._center_text(export_box, "Build JSONL/CSV")
        self._center_text(quit_box, "Exit")

        self._safe_addstr(height - 1, 2, self.menu.message[: max(0, width - 4)])

    def _render_game(self, height: int, width: int) -> None:
        assert self.session is not None
        state = self.session.state
        sidebar_w = max(26, min(30, width // 4))
        board_target_w = min(width - sidebar_w - 6, 12 + state.size * 5)
        board_box = Rect(1, 2, height - 2, max(56, board_target_w))
        sidebar_x = board_box.x + board_box.w + 2
        turn_box = Rect(1, sidebar_x, 8, width - sidebar_x - 2)
        menu_box = Rect(height - 11, sidebar_x, 5, width - sidebar_x - 2)
        quit_box = Rect(height - 5, sidebar_x, 4, width - sidebar_x - 2)

        for rect, title in [
            (board_box, "Board"),
            (turn_box, "Turn"),
            (menu_box, "Menu"),
            (quit_box, "Quit"),
        ]:
            self._draw_box(rect, title)

        self.hotspots = {
            "menu": menu_box,
            "quit": quit_box,
        }

        self._center_text(menu_box, "Back")
        self._center_text(quit_box, "Exit")

        self._draw_turn_panel(turn_box, state)
        self._draw_board(board_box, state)
        self._render_game_message(board_box, state)

    def handle_menu_input(self, key: int) -> None:
        if key in (ord("q"), ord("Q")):
            self.running = False
            return
        if key in (ord("p"), ord("P")):
            self.menu.cycle_p1()
            return
        if key in (ord("s"), ord("S")):
            self.menu.cycle_size()
            return
        if key in (10, 13, curses.KEY_ENTER):
            self._start_game()
            return
        if key == curses.KEY_MOUSE:
            self._handle_menu_mouse()

    def handle_game_input(self, key: int) -> None:
        session = self.session
        if session is None:
            self.view = "menu"
            return

        if key in (ord("q"), ord("Q")):
            self.running = False
            return
        if key in (ord("m"), ord("M")):
            self._return_to_menu()
            return
        if key == curses.KEY_MOUSE:
            self._handle_game_mouse()
            return

        controller = session.current_controller()
        if controller is not None:
            return

        row, col = session.selected
        if key == curses.KEY_UP:
            session.selected = (max(0, row - 1), col)
        elif key == curses.KEY_DOWN:
            session.selected = (min(session.state.size - 1, row + 1), col)
        elif key == curses.KEY_LEFT:
            session.selected = (row, max(0, col - 1))
        elif key == curses.KEY_RIGHT:
            session.selected = (row, min(session.state.size - 1, col + 1))
        elif key in (10, 13, curses.KEY_ENTER):
            self._attempt_human_move(row, col)

    def _start_game(self) -> None:
        config = GameConfig(
            board_size=self.menu.board_size,
            p1_type=self.menu.p1_type,
            p2_type=PlayerType.BASELINE,
        )
        engine = MatchEngine(config)
        state = engine.new_state()
        center = config.board_size // 2
        self.session = GameSession(
            config=config,
            engine=engine,
            state=state,
            metadata=new_match_metadata(config),
            controllers={
                Stone.BLACK: controller_for(config.p1_type),
                Stone.WHITE: controller_for(config.p2_type),
            },
            selected=(0, 0),
        )
        self.view = "game"

    def _return_to_menu(self) -> None:
        self.session = None
        self.view = "menu"
        self.menu.message = "Returned to menu. Unfinished games are discarded."

    def _step_ai(self, controller: PlayerController) -> None:
        assert self.session is not None
        start = time.perf_counter()
        context = PlayerContext(config=self.session.config, perspective=self.session.state.current_turn)
        try:
            move = controller.choose_move(self.session.state, context)
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.session.engine.apply_move(self.session.state, move.row, move.col, move.source, elapsed_ms)
            self.session.selected = (0, 0)
            self.session.message = (
                f"{move.stone.short_name.title()} played {chr(ord('A') + move.col)}{move.row + 1} "
                f"in {elapsed_ms:.1f} ms."
            )
            self._persist_if_finished()
            curses.napms(120)
        except Exception as exc:  # noqa: BLE001
            self.session.message = f"AI error: {exc}"

    def _attempt_human_move(self, row: int, col: int) -> None:
        assert self.session is not None
        try:
            self.session.engine.apply_move(self.session.state, row, col, "human", 0.0)
            self.session.selected = (0, 0)
            self.session.message = f"Placed at {chr(ord('A') + col)}{row + 1}."
            self._persist_if_finished()
        except InvalidMoveError:
            self.session.message = "Illegal move. Choose an empty point inside the board."

    def _persist_if_finished(self) -> None:
        assert self.session is not None
        if not self.session.state.is_finished or self.session.saved_path is not None:
            return
        self.session.metadata.finished_at = datetime.now(tz=UTC)
        path = save_finished_game(self.session.config, self.session.state, self.session.metadata)
        self.session.saved_path = str(path)
        if self.session.state.result is GameResult.DRAW:
            outcome = "Draw."
        else:
            outcome = f"{self.session.state.winner.short_name.title()} wins."
        self.session.message = f"{outcome} Saved to {path}."

    def _handle_menu_mouse(self) -> None:
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return
        if not (bstate & curses.BUTTON1_RELEASED):
            return
        if self._click_hit("p1", my, mx):
            self.menu.cycle_p1()
        elif self._click_hit("size", my, mx):
            self.menu.cycle_size()
        elif self._click_hit("start", my, mx):
            self._start_game()
        elif self._click_hit("export", my, mx):
            summary = export_games(GameConfig().data_dir, GameConfig().export_dir)
            self.menu.message = (
                f"Exported {summary.games} games / {summary.moves} moves "
                f"to {summary.jsonl_path} and {summary.csv_path}."
            )
        elif self._click_hit("quit", my, mx):
            self.running = False

    def _handle_game_mouse(self) -> None:
        assert self.session is not None
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return
        if not (bstate & curses.BUTTON1_RELEASED):
            return
        if self._click_hit("menu", my, mx):
            self._return_to_menu()
            return
        if self._click_hit("quit", my, mx):
            self.running = False
            return
        controller = self.session.current_controller()
        if controller is not None:
            return
        cell = self._board_cell_from_mouse(my, mx)
        if cell is None:
            return
        if cell == self.session.selected:
            self._attempt_human_move(*cell)
            return
        self.session.selected = cell
        self.session.message = f"Selected {chr(ord('A') + cell[1])}{cell[0] + 1}. Click again or press Enter."

    def _click_hit(self, name: str, y: int, x: int) -> bool:
        rect = self.hotspots.get(name)
        return rect.contains(y, x) if rect else False

    def _draw_box(self, rect: Rect, title: str | None = None) -> None:
        self.stdscr.attron(curses.A_BOLD)
        try:
            self.stdscr.addstr(rect.y, rect.x, "+" + "-" * (rect.w - 2) + "+")
            for offset in range(1, rect.h - 1):
                self.stdscr.addstr(rect.y + offset, rect.x, "|")
                self.stdscr.addstr(rect.y + offset, rect.x + rect.w - 1, "|")
            self.stdscr.addstr(rect.y + rect.h - 1, rect.x, "+" + "-" * (rect.w - 2) + "+")
            if title:
                self.stdscr.addstr(rect.y, rect.x + 2, f"[{title}]")
        except curses.error:
            pass
        finally:
            self.stdscr.attroff(curses.A_BOLD)

    def _draw_logo(self, rect: Rect) -> None:
        scale = 2
        word = "GOMOKU"
        glyph_width = len(LOGO_GLYPHS["G"][0]) * scale
        letter_gap = scale * 2
        total_width = glyph_width * len(word) + (len(word) - 1) * letter_gap
        total_height = len(LOGO_GLYPHS["G"]) * scale
        top = rect.y + max(2, (rect.h - total_height) // 2 - 1)
        left = rect.x + max(2, (rect.w - total_width) // 2)
        cursor = left
        for char in word:
            self._draw_pixel_glyph(LOGO_GLYPHS[char], top, cursor, scale)
            cursor += glyph_width + letter_gap

    def _draw_turn_panel(self, rect: Rect, state: GameState) -> None:
        turn_value = str(state.current_round).rjust(MAX_ROUND_DIGITS, "0")
        self._draw_digit_string(rect, turn_value)

    def _draw_digit_string(self, rect: Rect, text: str) -> None:
        scale = 1
        glyph_width = len(DIGIT_GLYPHS["0"][0])
        total_width = len(text) * glyph_width + max(0, len(text) - 1) * 2
        top = rect.y + max(1, (rect.h - len(DIGIT_GLYPHS["0"])) // 2)
        left = rect.x + max(2, (rect.w - total_width) // 2)
        cursor = left
        for char in text:
            glyph = DIGIT_GLYPHS.get(char)
            if glyph:
                self._draw_pixel_glyph(glyph, top, cursor, scale)
            cursor += glyph_width + 2

    def _draw_pixel_glyph(self, glyph: list[str], top: int, left: int, scale: int) -> None:
        pixels = {(r, c) for r, row in enumerate(glyph) for c, bit in enumerate(row) if bit == "1"}
        shadow_pixels = {
            (r, c + 1)
            for r, c in pixels
            if (r, c + 1) not in pixels
        }

        for r, c in shadow_pixels:
            for yy in range(scale):
                for xx in range(scale):
                    self._safe_addstr(top + r * scale + yy, left + c * scale + xx, SHADOW)
        for r, c in pixels:
            for yy in range(scale):
                for xx in range(scale):
                    self._safe_addstr(top + r * scale + yy, left + c * scale + xx, BLOCK)

    def _draw_board(self, rect: Rect, state: GameState) -> None:
        label_width = len(str(state.size)) + 1
        cell_width = 5
        usable_h = rect.h - 2
        row_step = 2 if self._can_use_double_row_spacing(usable_h, state.size) else 1
        grid_w = state.size * cell_width
        grid_h = 1 + (state.size - 1) * row_step
        board_w = label_width + grid_w
        board_h = grid_h + 1
        top = rect.y + max(1, (usable_h - board_h) // 2)
        left = rect.x + max(2, (rect.w - board_w) // 2)
        self.board_metrics = BoardMetrics(
            grid_top=top + 1,
            grid_left=left + label_width,
            cell_width=cell_width,
            row_step=row_step,
            size=state.size,
            label_width=label_width,
            board_width=board_w,
            board_height=board_h,
        )
        labels = "".join(chr(ord("A") + col).center(cell_width) for col in range(state.size))
        self._safe_addstr(top, left + label_width, labels)
        for row in range(state.size):
            row_y = top + 1 + row * row_step
            self._safe_addstr(row_y, left, str(row + 1).rjust(label_width - 1) + " ")
            for col in range(state.size):
                cell = self._board_cell_text(state.board[row][col], cell_width)
                x = left + label_width + col * cell_width
                attr = curses.A_REVERSE if self.session and self.session.selected == (row, col) else curses.A_NORMAL
                self._safe_addstr(row_y, x, cell, attr)

    def _board_cell_from_mouse(self, y: int, x: int) -> tuple[int, int] | None:
        if self.board_metrics is None or self.session is None:
            return None
        m = self.board_metrics
        grid_bottom = m.grid_top + 1 + (m.size - 1) * m.row_step
        if not (m.grid_top <= y < grid_bottom and m.grid_left <= x < m.grid_left + m.size * m.cell_width):
            return None
        row = round((y - m.grid_top) / m.row_step)
        col = (x - m.grid_left) // m.cell_width
        if 0 <= row < self.session.state.size and 0 <= col < self.session.state.size:
            return row, col
        return None

    def _board_cell_text(self, stone: Stone, cell_width: int) -> str:
        center = {
            Stone.EMPTY: ".",
            Stone.BLACK: "\u26ab",
            Stone.WHITE: "\u26aa",
        }[stone]
        return center.center(cell_width)

    def _can_use_double_row_spacing(self, usable_h: int, size: int) -> bool:
        needed = 1 + (size - 1) * 2 + 1
        return usable_h >= needed

    def _render_game_message(self, board_box: Rect, state: GameState) -> None:
        assert self.session is not None
        if state.is_finished:
            message = self.session.message
        else:
            status = f"{state.current_turn.short_name.title()} to move."
            message = f"{status} {self.session.message}"
        width = max(1, board_box.w - 4)
        lines = textwrap.wrap(message, width=width, break_long_words=False, break_on_hyphens=False) or [""]
        lines = lines[:2]
        start_y = board_box.y + board_box.h - 1 - len(lines)
        for index, line in enumerate(lines):
            self._safe_addstr(start_y + index, board_box.x + 2, line[:width])

    def _center_text(self, rect: Rect, text: str) -> None:
        y = rect.y + rect.h // 2
        x = rect.x + max(1, (rect.w - len(text)) // 2)
        self._safe_addstr(y, x, text)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass


def run_curses_app(stdscr: Any) -> int:
    return TerminalApp(stdscr).run()
