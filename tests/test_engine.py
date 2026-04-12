from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gomoku.engine import InvalidMoveError, MatchEngine
from gomoku.exporter import export_games
from gomoku.models import GameConfig, GameResult, PlayerType, Stone
from gomoku.persistence import load_saved_game, new_match_metadata, save_finished_game
from gomoku.players import BaselineAI, PlayerContext


class EngineTests(unittest.TestCase):
    def test_current_round_tracks_pairs_of_moves(self) -> None:
        engine = MatchEngine(GameConfig())
        state = engine.new_state()
        self.assertEqual(state.current_round, 1)
        engine.apply_move(state, 7, 7, "human")
        self.assertEqual(state.current_round, 1)
        engine.apply_move(state, 7, 8, "human")
        self.assertEqual(state.current_round, 2)

    def test_black_moves_first_and_alternates(self) -> None:
        engine = MatchEngine(GameConfig())
        state = engine.new_state()
        engine.apply_move(state, 7, 7, "human")
        self.assertEqual(state.history[0].stone, Stone.BLACK)
        self.assertEqual(state.current_turn, Stone.WHITE)

    def test_duplicate_move_is_rejected(self) -> None:
        engine = MatchEngine(GameConfig())
        state = engine.new_state()
        engine.apply_move(state, 7, 7, "human")
        with self.assertRaises(InvalidMoveError):
            engine.apply_move(state, 7, 7, "human")

    def test_detects_horizontal_five(self) -> None:
        engine = MatchEngine(GameConfig())
        state = engine.new_state()
        sequence = [(7, 3), (0, 0), (7, 4), (0, 1), (7, 5), (0, 2), (7, 6), (0, 3), (7, 7)]
        for row, col in sequence:
            engine.apply_move(state, row, col, "human")
        self.assertEqual(state.result, GameResult.BLACK_WIN)
        self.assertEqual(state.current_round, 5)

    def test_draw_when_board_fills(self) -> None:
        engine = MatchEngine(GameConfig(board_size=9))
        state = engine.new_state()
        pattern = [
            "BBWWBBWW.",
            "WWBBWWBBW",
            "BBWWBBWWB",
            "WWBBWWBBW",
            "BBWWBBWWB",
            "WWBBWWBBW",
            "BBWWBBWWB",
            "WWBBWWBBW",
            "BBWWBBWWB",
        ]
        for row, line in enumerate(pattern):
            for col, cell in enumerate(line):
                if cell == ".":
                    continue
                state.board[row][col] = Stone.BLACK if cell == "B" else Stone.WHITE
                state.ply += 1
        state.current_turn = Stone.BLACK
        engine.apply_move(state, 0, 8, "human")
        self.assertEqual(state.result, GameResult.DRAW)


class BaselineAITests(unittest.TestCase):
    def test_baseline_plays_center_on_empty_board(self) -> None:
        ai = BaselineAI()
        config = GameConfig()
        state = MatchEngine(config).new_state()
        move = ai.choose_move(state, PlayerContext(config, Stone.BLACK))
        self.assertEqual((move.row, move.col), (7, 7))

    def test_baseline_blocks_immediate_win(self) -> None:
        config = GameConfig()
        engine = MatchEngine(config)
        state = engine.new_state()
        for row, col in [(7, 7), (5, 5), (7, 8), (5, 6), (7, 9), (5, 7), (0, 0), (5, 8)]:
            engine.apply_move(state, row, col, "setup")
        ai = BaselineAI()
        move = ai.choose_move(state, PlayerContext(config, Stone.BLACK))
        self.assertIn((move.row, move.col), {(5, 4), (5, 9)})


class ExportTests(unittest.TestCase):
    def test_save_and_export_finished_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = GameConfig(data_dir=root / "games", export_dir=root / "exports", p1_type=PlayerType.BASELINE)
            engine = MatchEngine(config)
            state = engine.new_state()
            for row, col in [(4, 4), (0, 0), (4, 5), (0, 1), (4, 6), (0, 2), (4, 7), (0, 3), (4, 8)]:
                engine.apply_move(state, row, col, "baseline")
            metadata = new_match_metadata(config)
            path = save_finished_game(config, state, metadata)
            record = load_saved_game(path)
            self.assertEqual(record["result"], GameResult.BLACK_WIN.value)
            summary = export_games(config.data_dir, config.export_dir)
            self.assertEqual(summary.games, 1)
            self.assertTrue(summary.jsonl_path.exists())
            self.assertTrue(summary.csv_path.exists())


if __name__ == "__main__":
    unittest.main()
