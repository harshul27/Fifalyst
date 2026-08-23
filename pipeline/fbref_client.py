"""Optional FBref enrichment layer (via the `soccerdata` package).

FPL gives us reliable per-gameweek team/player numbers; FBref adds *tactical
depth* that FPL simply does not expose -- possession share, pass completion,
progressive passes, take-ons, touches by third.

Design constraint: FBref scrapes + rate-limits, and the first call can take
minutes. It is therefore strictly an ENRICHMENT layer -- every failure degrades
to "no extra columns" and never blocks a gameweek from being recorded.

ponytail: season-to-date cumulative, snapshotted per GW. True per-GW deltas
would need match-level tables; the snapshot is enough to show tactical trend.
"""
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# FPL short names -> FBref names.
FPL_TO_FBREF = {
    "Man City": "Manchester City",
    "Man Utd": "Manchester Utd",
    "Spurs": "Tottenham",
    "Nott'm Forest": "Nott'ham Forest",
    "Newcastle": "Newcastle Utd",
    "Leeds": "Leeds United",
    "Brighton": "Brighton",
    "Wolves": "Wolves",
    "Sheffield Utd": "Sheffield Utd",
}

# (stat_type, FBref column tuple) -> output column name.
_WANTED = {
    "possession": {
        ("Poss", ""): "possession_pct",
        ("Touches", "Att 3rd"): "touches_att_3rd",
        ("Touches", "Def 3rd"): "touches_def_3rd",
        ("Take-Ons", "Succ"): "take_ons_succ",
        ("Carries", "PrgC"): "progressive_carries",
    },
    "passing": {
        ("Total", "Cmp%"): "pass_completion_pct",
        ("Total", "Cmp"): "passes_completed",
        ("Long", "Cmp%"): "long_pass_pct",
        ("", "PrgP"): "progressive_passes",
        ("KP", ""): "key_passes",
    },
}


class FBrefClient:
    """Thin, fail-soft wrapper around soccerdata.FBref team season stats."""

    def __init__(self, season: str = "2026-2027", league: str = "ENG-Premier League"):
        self.season = season
        self.league = league

    def _read(self, stat_type: str) -> Optional[pd.DataFrame]:
        try:
            import soccerdata as sd
            fb = sd.FBref(leagues=self.league, seasons=self.season)
            return fb.read_team_season_stats(stat_type=stat_type)
        except Exception as e:  # network, rate-limit, missing season, parse drift
            logger.warning(f"FBref {stat_type} unavailable ({type(e).__name__}) - skipping enrichment")
            return None

    def team_tactical_snapshot(self) -> pd.DataFrame:
        """Per-team tactical columns. Empty frame if FBref is unreachable."""
        out = pd.DataFrame()
        for stat_type, wanted in _WANTED.items():
            df = self._read(stat_type)
            if df is None or df.empty:
                continue
            teams = df.index.get_level_values("team")
            picked = pd.DataFrame({"fbref_team": teams})
            for col, name in wanted.items():
                if col in df.columns:
                    picked[name] = df[col].values
            out = picked if out.empty else out.merge(picked, on="fbref_team", how="outer")
        return out

    def player_baseline_quality(self, seasons=("2025-2026", "2024-2025")) -> pd.DataFrame:
        """Per-90 output from PREVIOUS seasons -> a player-ability baseline.

        The StatsBomb corpus supplies in-match state; FBref history supplies how
        good a player actually is, which is what makes a bench option worth
        bringing on. Minutes-weighted across seasons. Fail-soft like the rest.
        """
        frames = []
        for season in seasons:
            try:
                import soccerdata as sd
                fb = sd.FBref(leagues=self.league, seasons=season)
                df = fb.read_player_season_stats(stat_type="standard")
            except Exception as e:
                logger.warning(f"FBref players {season} unavailable ({type(e).__name__})")
                continue
            flat = pd.DataFrame(index=df.index)
            for src, dst in [(("Playing Time", "Min"), "minutes"),
                             (("Per 90 Minutes", "npxG"), "npxg_p90"),
                             (("Per 90 Minutes", "xAG"), "xag_p90"),
                             (("Per 90 Minutes", "G+A"), "ga_p90")]:
                if src in df.columns:
                    flat[dst] = pd.to_numeric(df[src], errors="coerce")
            flat = flat.reset_index()
            flat["season"] = season
            frames.append(flat)

        if not frames:
            return pd.DataFrame()

        allp = pd.concat(frames, ignore_index=True)
        key = "player" if "player" in allp.columns else allp.columns[0]
        allp["minutes"] = allp.get("minutes", pd.Series(0, index=allp.index)).fillna(0)

        def wavg(g, col):
            w = g["minutes"].sum()
            return float((g[col] * g["minutes"]).sum() / w) if w > 0 and col in g else float("nan")

        out = (allp.groupby(key)
               .apply(lambda g: pd.Series({
                   "minutes": float(g["minutes"].sum()),
                   "npxg_p90": wavg(g, "npxg_p90"),
                   "xag_p90": wavg(g, "xag_p90"),
                   "ga_p90": wavg(g, "ga_p90"),
               }), include_groups=False)
               .reset_index())
        # bounded 0-1 ability score; minutes act as a confidence weight
        contrib = out[["npxg_p90", "xag_p90"]].sum(axis=1, min_count=1)
        out["quality_score"] = (contrib.rank(pct=True)).fillna(0.5)
        return out

    def enrich_teams(self, teams: pd.DataFrame) -> pd.DataFrame:
        """Left-join FBref tactical columns onto FPL-derived team rows."""
        snap = self.team_tactical_snapshot()
        if snap.empty or teams.empty:
            return teams
        teams = teams.copy()
        teams["fbref_team"] = teams["team"].map(lambda t: FPL_TO_FBREF.get(t, t))
        merged = teams.merge(snap, on="fbref_team", how="left").drop(columns=["fbref_team"])
        matched = merged.get("possession_pct", pd.Series(dtype=float)).notna().sum()
        logger.info(f"✓ FBref enrichment matched {matched}/{len(teams)} teams")
        return merged


def demo():
    """Offline check: enrichment must degrade cleanly when FBref is unavailable."""
    teams = pd.DataFrame({"team": ["Man City", "Arsenal"], "goals_scored": [2, 1]})

    class Down(FBrefClient):
        def team_tactical_snapshot(self):
            return pd.DataFrame()

    out = Down().enrich_teams(teams)
    assert len(out) == 2 and "goals_scored" in out.columns, "must pass through unchanged"

    class Up(FBrefClient):
        def team_tactical_snapshot(self):
            return pd.DataFrame({"fbref_team": ["Manchester City", "Arsenal"],
                                 "possession_pct": [65.0, 58.0]})

    out = Up().enrich_teams(teams)
    assert out.loc[out["team"] == "Man City", "possession_pct"].iloc[0] == 65.0, "name mapping failed"
    assert "fbref_team" not in out.columns
    # previous-season baseline must degrade cleanly too
    class NoPlayers(FBrefClient):
        def player_baseline_quality(self, seasons=("2025-2026",)):
            return pd.DataFrame()

    assert NoPlayers().player_baseline_quality().empty

    print("fbref_client self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo()
