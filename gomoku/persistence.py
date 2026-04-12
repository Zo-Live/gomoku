from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import GameConfig, GameState, MoveRecord, PlayerType, Stone
from .rules import coord_to_label


@dataclass(slots=True)
class MatchMetadata:
    match_id: str
    started_at: datetime
    finished_at: datetime | None = None
    black_player: PlayerType = PlayerType.HUMAN
    white_player: PlayerType = PlayerType.BASELINE


def new_match_metadata(config: GameConfig) -> MatchMetadata:
    timestamp = datetime.now(tz=UTC)
    return MatchMetadata(
        match_id=f"{timestamp.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}",
        started_at=timestamp,
        black_player=config.p1_type,
        white_player=config.p2_type,
    )


def save_finished_game(config: GameConfig, state: GameState, metadata: MatchMetadata) -> Path:
    if not state.is_finished:
        raise ValueError("cannot save an unfinished game")

    metadata.finished_at = metadata.finished_at or datetime.now(tz=UTC)
    record = serialize_game(config, state, metadata)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    path = config.data_dir / f"{metadata.match_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def serialize_game(config: GameConfig, state: GameState, metadata: MatchMetadata) -> dict[str, object]:
    return {
        "match_id": metadata.match_id,
        "started_at": metadata.started_at.isoformat(),
        "finished_at": metadata.finished_at.isoformat() if metadata.finished_at else None,
        "config": {
            "board_size": config.board_size,
            "allow_draw": config.allow_draw,
        },
        "players": {
            "black": metadata.black_player.value,
            "white": metadata.white_player.value,
        },
        "result": state.result.value if state.result else None,
        "winner": state.winner.short_name if state.winner else None,
        "end_reason": state.end_reason,
        "total_plies": state.ply,
        "moves": [serialize_move(move) for move in state.history],
        "final_board": board_snapshot(state),
    }


def serialize_move(move: MoveRecord) -> dict[str, object]:
    return {
        "ply": move.ply,
        "player": move.stone.short_name,
        "row": move.row,
        "col": move.col,
        "coord": coord_to_label(move.row, move.col),
        "source": move.source,
        "elapsed_ms": round(move.elapsed_ms, 3),
    }


def board_snapshot(state: GameState) -> list[str]:
    mapping = {
        Stone.EMPTY: ".",
        Stone.BLACK: "B",
        Stone.WHITE: "W",
    }
    return ["".join(mapping[cell] for cell in row) for row in state.board]


def load_saved_game(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
