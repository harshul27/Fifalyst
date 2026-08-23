"""Pluggable slot for physical / tracking statistics.

Physical data (distance covered, sprints, high-speed running, top speed) comes
from tracking/Opta providers and has no free, reliable source. The default
adapter is a no-op that adds the physical columns as NaN so the schema and
dashboard are ready the moment a real source is wired in -- deliberately NO
fake numbers.

Upgrade path: subclass PhysicalStatsAdapter and override `enrich` to fill the
PHYSICAL_COLS from a paid API (e.g. Sofascore/Opta premium) or an imported CSV,
keyed by player_id + gw.
"""
import numpy as np
import pandas as pd

PHYSICAL_COLS = ["distance_km", "sprints", "high_speed_running_m", "top_speed_kmh"]


class PhysicalStatsAdapter:
    """No-op default: guarantees the physical columns exist (as NaN)."""

    def enrich(self, players: pd.DataFrame) -> pd.DataFrame:
        for col in PHYSICAL_COLS:
            if col not in players.columns:
                players[col] = np.nan
        return players


def demo():
    df = pd.DataFrame({"player_id": [1, 2], "minutes": [90, 45]})
    out = PhysicalStatsAdapter().enrich(df)
    assert all(c in out.columns for c in PHYSICAL_COLS)
    assert out["distance_km"].isna().all(), "default adapter must not invent numbers"
    print("physical_adapter self-check OK")


if __name__ == "__main__":
    demo()
