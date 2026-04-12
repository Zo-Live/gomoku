from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .persistence import load_saved_game


@dataclass(slots=True)
class ExportSummary:
    games: int
    moves: int
    jsonl_path: Path
    csv_path: Path


def export_games(data_dir: Path, output_dir: Path) -> ExportSummary:
    output_dir.mkdir(parents=True, exist_ok=True)
    game_files = sorted(data_dir.glob("*.json")) if data_dir.exists() else []

    jsonl_path = output_dir / "games.jsonl"
    csv_path = output_dir / "moves.csv"

    move_count = 0
    with jsonl_path.open("w", encoding="utf-8") as jsonl_handle, csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_handle:
        writer = csv.DictWriter(
            csv_handle,
            fieldnames=[
                "match_id",
                "ply",
                "player",
                "row",
                "col",
                "coord",
                "elapsed_ms",
                "board_size",
                "result",
            ],
        )
        writer.writeheader()

        for path in game_files:
            record = load_saved_game(path)
            jsonl_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            moves = record.get("moves", [])
            config = record.get("config", {})
            for move in moves:
                move_count += 1
                writer.writerow(
                    {
                        "match_id": record.get("match_id"),
                        "ply": move.get("ply"),
                        "player": move.get("player"),
                        "row": move.get("row"),
                        "col": move.get("col"),
                        "coord": move.get("coord"),
                        "elapsed_ms": move.get("elapsed_ms"),
                        "board_size": config.get("board_size"),
                        "result": record.get("result"),
                    }
                )

    return ExportSummary(games=len(game_files), moves=move_count, jsonl_path=jsonl_path, csv_path=csv_path)
