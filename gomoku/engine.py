from __future__ import annotations

from dataclasses import dataclass

from .models import GameConfig, GameResult, GameState, MoveRecord, Stone
from .rules import detect_five, is_board_full, is_legal_move


class InvalidMoveError(ValueError):
    """Raised when a move cannot be applied."""


@dataclass(slots=True)
class MatchEngine:
    config: GameConfig

    def new_state(self) -> GameState:
        return GameState.empty(self.config.board_size)

    def apply_move(self, state: GameState, row: int, col: int, source: str, elapsed_ms: float = 0.0) -> MoveRecord:
        if not is_legal_move(state, row, col):
            raise InvalidMoveError(f"illegal move ({row}, {col})")

        stone = state.current_turn
        record = MoveRecord(
            row=row,
            col=col,
            stone=stone,
            source=source,
            ply=state.ply + 1,
            elapsed_ms=elapsed_ms,
        )

        state.board[row][col] = stone
        state.ply += 1
        state.last_move = record
        state.history.append(record)

        if detect_five(state.board, row, col, stone):
            state.winner = stone
            state.result = GameResult.BLACK_WIN if stone is Stone.BLACK else GameResult.WHITE_WIN
            state.end_reason = "five_in_a_row"
            return record

        if self.config.allow_draw and is_board_full(state.board):
            state.result = GameResult.DRAW
            state.end_reason = "board_full"
            return record

        state.current_turn = stone.opponent()
        return record

    def abort(self, state: GameState, reason: str = "aborted") -> None:
        state.result = GameResult.ABORTED
        state.end_reason = reason
