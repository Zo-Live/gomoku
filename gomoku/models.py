from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Stone(str, Enum):
    EMPTY = "."
    BLACK = "black"
    WHITE = "white"

    def opponent(self) -> "Stone":
        if self is Stone.BLACK:
            return Stone.WHITE
        if self is Stone.WHITE:
            return Stone.BLACK
        return Stone.EMPTY

    @property
    def glyph(self) -> str:
        return {
            Stone.EMPTY: "·",
            Stone.BLACK: "●",
            Stone.WHITE: "○",
        }[self]

    @property
    def short_name(self) -> str:
        return {
            Stone.EMPTY: "empty",
            Stone.BLACK: "black",
            Stone.WHITE: "white",
        }[self]


class PlayerType(str, Enum):
    HUMAN = "human"
    BASELINE = "baseline"
    SEARCH = "search"


class GameResult(str, Enum):
    BLACK_WIN = "black_win"
    WHITE_WIN = "white_win"
    DRAW = "draw"
    ABORTED = "aborted"


@dataclass(slots=True)
class GameConfig:
    board_size: int = 15
    allow_draw: bool = True
    p1_type: PlayerType = PlayerType.HUMAN
    p2_type: PlayerType = PlayerType.BASELINE
    data_dir: Path = Path("data/games")
    export_dir: Path = Path("exports")

    def __post_init__(self) -> None:
        if self.board_size < 9 or self.board_size > 19 or self.board_size % 2 == 0:
            raise ValueError("board_size must be an odd integer between 9 and 19")


@dataclass(slots=True)
class Move:
    row: int
    col: int
    stone: Stone
    source: str


@dataclass(slots=True)
class MoveRecord(Move):
    ply: int
    elapsed_ms: float = 0.0


@dataclass(slots=True)
class Prediction:
    black_rate: float
    white_rate: float


@dataclass(slots=True)
class GameState:
    board: list[list[Stone]]
    current_turn: Stone = Stone.BLACK
    ply: int = 0
    result: GameResult | None = None
    winner: Stone | None = None
    end_reason: str = ""
    last_move: MoveRecord | None = None
    history: list[MoveRecord] = field(default_factory=list)

    @classmethod
    def empty(cls, size: int) -> "GameState":
        return cls(board=[[Stone.EMPTY for _ in range(size)] for _ in range(size)])

    @property
    def size(self) -> int:
        return len(self.board)

    @property
    def is_finished(self) -> bool:
        return self.result is not None

    @property
    def current_round(self) -> int:
        if self.is_finished:
            return max(1, (self.ply + 1) // 2)
        return self.ply // 2 + 1

    def clone(self) -> "GameState":
        return GameState(
            board=[row[:] for row in self.board],
            current_turn=self.current_turn,
            ply=self.ply,
            result=self.result,
            winner=self.winner,
            end_reason=self.end_reason,
            last_move=self.last_move,
            history=self.history[:],
        )
