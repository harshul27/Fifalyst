"""Per-gameweek parquet store for the PL 2026/27 season.

Layout (idempotent -- re-recording a GW overwrites its files):
    data/pl_2026_27/
        gw{n}/players.parquet
        gw{n}/teams.parquet
        meta.json   -> {"gameweeks": {n: {final, updated_at, n_players, n_teams}}, ...}

Season/cumulative views are computed on demand by concatenating GW files, so
there is no separate aggregate table to keep in sync.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class SeasonStore:
    def __init__(self, base: str = "data/pl_2026_27"):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.base / "meta.json"

    def _gw_dir(self, gw: int) -> Path:
        return self.base / f"gw{gw}"

    # ---- meta ----
    def meta(self) -> dict:
        if self.meta_path.exists():
            return json.loads(self.meta_path.read_text())
        return {"season": "2026-27", "gameweeks": {}, "updated_at": None}

    def _write_meta(self, meta: dict):
        self.meta_path.write_text(json.dumps(meta, indent=2))

    def recorded_gameweeks(self) -> Dict[int, dict]:
        """gw -> {final, updated_at, ...}."""
        return {int(k): v for k, v in self.meta().get("gameweeks", {}).items()}

    # ---- write ----
    def write_gameweek(self, gw: int, players: pd.DataFrame, teams: pd.DataFrame,
                       final: bool = False) -> None:
        d = self._gw_dir(gw)
        d.mkdir(parents=True, exist_ok=True)
        players.to_parquet(d / "players.parquet", index=False)
        teams.to_parquet(d / "teams.parquet", index=False)

        meta = self.meta()
        meta["gameweeks"][str(gw)] = {
            "final": final,
            "n_players": int(len(players)),
            "n_teams": int(len(teams)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_meta(meta)
        logger.info(f"✓ stored GW{gw}: {len(players)} players, {len(teams)} teams (final={final})")

    # ---- read ----
    def read_gameweek(self, gw: int) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        d = self._gw_dir(gw)
        p = pd.read_parquet(d / "players.parquet") if (d / "players.parquet").exists() else None
        t = pd.read_parquet(d / "teams.parquet") if (d / "teams.parquet").exists() else None
        return p, t

    def read_season(self, kind: str = "players") -> pd.DataFrame:
        """Concatenate every recorded GW's players|teams into one frame."""
        assert kind in ("players", "teams")
        frames = []
        for gw in sorted(self.recorded_gameweeks()):
            f = self._gw_dir(gw) / f"{kind}.parquet"
            if f.exists():
                frames.append(pd.read_parquet(f))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def demo():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        s = SeasonStore(base=f"{tmp}/pl")
        players = pd.DataFrame({"gw": [1, 1], "player_id": [1, 2], "goals_scored": [1, 0]})
        teams = pd.DataFrame({"gw": [1], "team": ["Arsenal"], "goals": [1]})
        s.write_gameweek(1, players, teams, final=False)
        assert s.recorded_gameweeks() == {1: s.recorded_gameweeks()[1]}
        assert s.recorded_gameweeks()[1]["final"] is False
        p, t = s.read_gameweek(1)
        assert len(p) == 2 and len(t) == 1
        # re-record overwrites, flips final
        s.write_gameweek(1, players, teams, final=True)
        assert s.recorded_gameweeks()[1]["final"] is True
        assert len(s.read_season("players")) == 2
    print("season_store self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo()
