from __future__ import annotations

from typing import Iterable

from .models import GameState, Stone

DIRECTIONS: tuple[tuple[int, int], ...] = ((1, 0), (0, 1), (1, 1), (1, -1))


def is_on_board(size: int, row: int, col: int) -> bool:
    return 0 <= row < size and 0 <= col < size


def is_legal_move(state: GameState, row: int, col: int) -> bool:
    return is_on_board(state.size, row, col) and state.board[row][col] is Stone.EMPTY and not state.is_finished


def is_board_full(board: list[list[Stone]]) -> bool:
    return all(cell is not Stone.EMPTY for row in board for cell in row)


def coord_to_label(row: int, col: int) -> str:
    return f"{chr(ord('A') + col)}{row + 1}"


def label_to_coord(label: str) -> tuple[int, int]:
    label = label.strip().upper()
    if len(label) < 2:
        raise ValueError("invalid coordinate label")
    col = ord(label[0]) - ord("A")
    row = int(label[1:]) - 1
    return row, col


def count_consecutive(
    board: list[list[Stone]],
    row: int,
    col: int,
    stone: Stone,
    dr: int,
    dc: int,
) -> int:
    size = len(board)
    count = 0
    r = row + dr
    c = col + dc
    while is_on_board(size, r, c) and board[r][c] is stone:
        count += 1
        r += dr
        c += dc
    return count


def detect_five(board: list[list[Stone]], row: int, col: int, stone: Stone) -> bool:
    for dr, dc in DIRECTIONS:
        total = 1
        total += count_consecutive(board, row, col, stone, dr, dc)
        total += count_consecutive(board, row, col, stone, -dr, -dc)
        if total >= 5:
            return True
    return False


def line_length_and_openness(
    board: list[list[Stone]],
    row: int,
    col: int,
    stone: Stone,
    dr: int,
    dc: int,
) -> tuple[int, int]:
    size = len(board)
    forward = 0
    r = row + dr
    c = col + dc
    while is_on_board(size, r, c) and board[r][c] is stone:
        forward += 1
        r += dr
        c += dc
    open_ends = 1 if is_on_board(size, r, c) and board[r][c] is Stone.EMPTY else 0

    backward = 0
    r = row - dr
    c = col - dc
    while is_on_board(size, r, c) and board[r][c] is stone:
        backward += 1
        r -= dr
        c -= dc
    if is_on_board(size, r, c) and board[r][c] is Stone.EMPTY:
        open_ends += 1

    return 1 + forward + backward, open_ends


def iter_legal_moves(state: GameState) -> Iterable[tuple[int, int]]:
    for row in range(state.size):
        for col in range(state.size):
            if state.board[row][col] is Stone.EMPTY:
                yield row, col


def neighbor_candidates(state: GameState, radius: int = 2) -> list[tuple[int, int]]:
    occupied = [(row, col) for row in range(state.size) for col in range(state.size) if state.board[row][col] is not Stone.EMPTY]
    if not occupied:
        center = state.size // 2
        return [(center, center)]

    seen: set[tuple[int, int]] = set()
    for row, col in occupied:
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                rr = row + dr
                cc = col + dc
                if is_on_board(state.size, rr, cc) and state.board[rr][cc] is Stone.EMPTY:
                    seen.add((rr, cc))
    return sorted(seen)
