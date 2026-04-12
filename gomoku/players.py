from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import GameConfig, GameState, Move, PlayerType, Prediction, Stone
from .rules import DIRECTIONS, detect_five, is_legal_move, line_length_and_openness, neighbor_candidates


@dataclass(slots=True)
class PlayerContext:
    config: GameConfig
    perspective: Stone


class PlayerController(Protocol):
    def choose_move(self, state: GameState, context: PlayerContext) -> Move:
        """Return a legal move."""


class PredictionProvider(Protocol):
    def predict(self, state: GameState) -> Prediction | None:
        """Return a display prediction for the current state."""


class Evaluator(Protocol):
    def score(self, state: GameState, perspective: Stone) -> int:
        """Return a static evaluation score."""


class CandidateGenerator(Protocol):
    def generate(self, state: GameState, perspective: Stone) -> list[Move]:
        """Return candidate moves for search."""


@dataclass(slots=True)
class SearchDecision:
    move: Move
    score: int
    depth: int
    nodes: int


class SearchPolicy(Protocol):
    def search(self, state: GameState, perspective: Stone, limit: int) -> SearchDecision:
        """Search for the next move."""


@dataclass(slots=True)
class NullPredictionProvider:
    def predict(self, state: GameState) -> Prediction | None:
        return None


@dataclass(slots=True)
class BaselineAI:
    name: str = "baseline"
    neighbor_radius: int = 2

    def choose_move(self, state: GameState, context: PlayerContext) -> Move:
        candidates = neighbor_candidates(state, radius=self.neighbor_radius)
        stone = context.perspective
        opponent = stone.opponent()

        for row, col in candidates:
            if self._is_winning_move(state, row, col, stone):
                return Move(row=row, col=col, stone=stone, source=self.name)

        for row, col in candidates:
            if self._is_winning_move(state, row, col, opponent):
                return Move(row=row, col=col, stone=stone, source=self.name)

        scored: list[tuple[tuple[float, float, int, int], tuple[int, int]]] = []
        for row, col in candidates:
            if not is_legal_move(state, row, col):
                continue
            score = self._score_candidate(state, row, col, stone)
            center_bias = -self._distance_to_center(state.size, row, col)
            scored.append(((score, center_bias, -row, -col), (row, col)))

        if scored:
            scored.sort(reverse=True)
            row, col = scored[0][1]
            return Move(row=row, col=col, stone=stone, source=self.name)

        for row in range(state.size):
            for col in range(state.size):
                if is_legal_move(state, row, col):
                    return Move(row=row, col=col, stone=stone, source=self.name)

        raise RuntimeError("no legal moves available")

    def _is_winning_move(self, state: GameState, row: int, col: int, stone: Stone) -> bool:
        if state.board[row][col] is not Stone.EMPTY:
            return False
        state.board[row][col] = stone
        try:
            return detect_five(state.board, row, col, stone)
        finally:
            state.board[row][col] = Stone.EMPTY

    def _score_candidate(self, state: GameState, row: int, col: int, stone: Stone) -> float:
        state.board[row][col] = stone
        try:
            attack = self._pattern_score(state, row, col, stone)
        finally:
            state.board[row][col] = Stone.EMPTY

        state.board[row][col] = stone.opponent()
        try:
            defense = self._pattern_score(state, row, col, stone.opponent())
        finally:
            state.board[row][col] = Stone.EMPTY

        adjacency = self._adjacency_score(state, row, col, stone)
        return attack * 1.8 + defense * 1.4 + adjacency

    def _pattern_score(self, state: GameState, row: int, col: int, stone: Stone) -> int:
        best = 0
        total = 0
        for dr, dc in DIRECTIONS:
            length, open_ends = line_length_and_openness(state.board, row, col, stone, dr, dc)
            value = self._weight_pattern(length, open_ends)
            best = max(best, value)
            total += value
        return best * 2 + total

    @staticmethod
    def _weight_pattern(length: int, open_ends: int) -> int:
        if length >= 5:
            return 100_000
        if length == 4 and open_ends == 2:
            return 20_000
        if length == 4 and open_ends == 1:
            return 5_000
        if length == 3 and open_ends == 2:
            return 1_500
        if length == 3 and open_ends == 1:
            return 400
        if length == 2 and open_ends == 2:
            return 120
        if length == 2 and open_ends == 1:
            return 40
        return 10

    def _adjacency_score(self, state: GameState, row: int, col: int, stone: Stone) -> int:
        total = 0
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                if dr == 0 and dc == 0:
                    continue
                rr = row + dr
                cc = col + dc
                if 0 <= rr < state.size and 0 <= cc < state.size:
                    if state.board[rr][cc] is stone:
                        total += 12
                    elif state.board[rr][cc] is stone.opponent():
                        total += 8
        return total

    @staticmethod
    def _distance_to_center(size: int, row: int, col: int) -> int:
        center = size // 2
        return abs(row - center) + abs(col - center)


@dataclass(slots=True)
class SearchAI:
    fallback: BaselineAI = field(default_factory=lambda: BaselineAI(name="search-fallback"))

    def choose_move(self, state: GameState, context: PlayerContext) -> Move:
        return self.fallback.choose_move(state, context)


def controller_for(player_type: PlayerType) -> PlayerController | None:
    if player_type is PlayerType.BASELINE:
        return BaselineAI()
    if player_type is PlayerType.SEARCH:
        return SearchAI()
    return None
