# Premier League 2026/27 - Season Stats Recorder

Records **every played gameweek (1-38)** of the 2026/27 Premier League season:
per-player statistics across all gameplay categories, and per-team attacking /
midfield / defensive profiles with derived tactical indicators.

Season kicked off **21 August 2026**.

## Quick start

```bash
pip install -r requirements.txt

python record.py                       # record every played GW not yet final
python -m streamlit run pl_season_app.py   # dashboard at http://localhost:8501
```

## How it works

```
FPL API  ──►  SeasonOrchestrator  ──►  parquet per gameweek  ──►  Streamlit
(per-GW)      + physical adapter       data/pl_2026_27/gw{n}/     dashboard
              + team aggregation
              + FBref (optional)
```

1. **Fetch** - `pipeline/fpl_client.py` pulls per-player stats for a gameweek
   from the official FPL API (public, no key, no bot-blocking).
2. **Enrich** - `pipeline/physical_adapter.py` adds the physical-stat columns
   (see caveat below). `--fbref` optionally layers FBref tactical depth.
3. **Aggregate** - `pipeline/team_stats.py` rolls player rows into per-team
   attacking / midfield / defensive buckets plus tactical indicators.
4. **Store** - `pipeline/season_store.py` writes parquet per gameweek.
   Re-running is idempotent.
5. **View** - `pl_season_app.py` browses any gameweek or the season to date.

### Recording model

A gameweek is recorded as soon as it has been played, and **re-recorded on each
run until FPL marks it `finished` and `data_checked`**. This matters: FPL does
not publish the ICT family (influence / creativity / threat) while a gameweek
is still in progress, so an in-progress GW self-heals into complete data once
finalised. `--status` shows which gameweeks are final.

## Commands

```bash
python record.py                # record played GWs that aren't final yet
python record.py --gw 5         # record one gameweek
python record.py --all          # force re-record everything
python record.py --fbref        # add FBref tactical enrichment (slow, scrapes)
python record.py --status       # list recorded gameweeks
```

Run it after each gameweek (or on a weekly cron) to build the season.

## What's recorded

**Per player** - minutes, starts, goals, assists, xG, xA, xGI, goals conceded,
xGC, clean sheets, saves, penalties saved/missed, own goals, tackles,
clearances+blocks+interceptions, recoveries, defensive contribution, yellow and
red cards, influence, creativity, threat, ICT index, bonus, BPS, total points.

**Per team** - all of the above aggregated, plus `clean_sheet`,
`finishing_edge` (goals minus xG), `defensive_actions`, `directness`
(threat vs creativity) and an auto-generated `tactical_label`
(e.g. *"high-xG, solid, possession-based"*).

With `--fbref`: possession %, pass completion %, long-pass %, progressive
passes, progressive carries, successful take-ons, touches by third.

## Physical statistics: intentionally empty

Distance covered, sprints, high-speed running and top speed come from tracking
providers (Opta/Second Spectrum) with **no free public feed**. The columns exist
in the schema and the dashboard shows a Physical tab, but the values stay empty
rather than being filled with estimates or mock numbers.

To connect a real source, subclass `PhysicalStatsAdapter` in
`pipeline/physical_adapter.py` and fill `PHYSICAL_COLS` keyed by
`player_id` + `gw`. Nothing else needs to change.

## Data layout

```
data/pl_2026_27/
  gw1/players.parquet   # one row per player who featured
  gw1/teams.parquet     # one row per team that played
  meta.json             # per-GW final/in-progress status
```

## Verify

```bash
python -m pipeline.fpl_client       # live API self-check
python -m pipeline.season_store     # storage round-trip
python -m pipeline.team_stats       # aggregation + tactical labels
python -m pipeline.fbref_client     # enrichment degrades cleanly when offline
python test_fpl_client.py           # end-to-end smoke test
```

## Substitution & tactics coach (trained model)

A model that ranks who to bring off, and suggests tactical shifts, from live
match state. Trained on **StatsBomb open data** (men's competitions) with
**FBref** previous seasons supplying player-ability baselines.

### Two layers, validated differently

**1. Timing model** - `P(player substituted off within the next 5 minutes)`,
learned from real coach decisions. Features: minutes played, involvement decay
vs the player's own match baseline, recent pass accuracy, booking status,
pressures/duels, position, plus team state (goal difference, subs used, rolling
xG for/against, possession share, field tilt).

Validated with **GroupKFold on match_id** (no match spans folds) and a
**held-out competition never seen in training**, scored against explicit
heuristic baselines and checked for probability calibration.

**2. Impact layer** - measured post-substitution momentum swing, aggregated by
game state x minute bucket, used to re-rank candidates the timing model already
surfaced. This is observational and confounded (coaches sub *because* they are
chasing a game), so it is a bounded prior, never a causal claim.

### What the model actually keys on

Measured by holding every other feature constant and sweeping one:

| Driver | Effect on withdrawal probability | Verdict |
|---|---|---|
| Minutes played (35' -> 85') | 0.003 -> 0.127 | dominant, monotonic |
| Position (DEF / MID / FWD) | 0.040 / 0.109 / 0.114 | strong - defenders are rotated far less |
| Booking | +0.023 | correct direction |
| Recent involvement | weak, U-shaped | see below |
| Recent pass accuracy | ~flat | not used |

The intuitive "tired player fades, therefore gets subbed" signal is **much weaker
than expected**. In the corpus the relationship is U-shaped: players who fade
badly are withdrawn (3.1%), and so are players with surging involvement (2.9%) -
usually the attackers coaches rotate - while steady players stay on (1.9%).
An explicit `involvement_anomaly` feature was added to express that shape; it
moved the metrics by less than noise, and is kept only because the shape is real.

Practical consequence: this behaves like a **workload-and-role model**, not a
fatigue detector. Real fatigue detection needs the physical/tracking data that
`pipeline/physical_adapter.py` is the slot for - distance, sprints and
high-speed-running decay are the signals that would actually carry it.

### Honest scope

The timing model learns **what coaches do**, not what is provably optimal.
That is the only target this data can support rigorously. It is genuinely
useful - it catches fatigue, fading influence and booking risk the way
experienced coaches do - but it is not proof that a recommended change wins
matches.

### Train it

```bash
python train_sub_model.py --extract     # extract corpus, then train (slow first time)
python train_sub_model.py               # retrain from cached features
python train_sub_model.py --holdout "La Liga"
```

Prints CV + held-out metrics, baseline comparison, calibration table and the
impact prior. Saves `models/sub_timing_model.pkl` and `sub_model_report.json`.

### Use it

```python
from orchestrator import get_orchestrator
from pipeline.sub_recommender import MatchState, PlayerState

orch = get_orchestrator()
match = MatchState(minute=70, goal_diff=-1, subs_used=1,
                   team_xg_w=0.2, opp_xg_w=0.7, possession_w=0.38, field_tilt_w=0.18)
recs = orch.recommend_subs(players, match, bench=bench, tracker=tracker)
advice = orch.tactical_advice(match)
```

Pass a `SubstitutionTracker` and the 5-substitution limit is enforced and
players already withdrawn are excluded automatically.

The **Match Coach** tab in the dashboard exposes this interactively, with the
model's report card shown up front.

## Live in-match tracking & coaching

```bash
python train_live_model.py        # one-time: train the FPL-feedable model
python live_coach.py              # follow the current gameweek, poll every 2 min
python live_coach.py --once       # single poll
python live_coach.py --evaluate   # score logged recommendations vs real subs
```

Also exposed as the **Live Tracking** tab in the dashboard.

### How it reconstructs live state

FPL publishes cumulative per-player totals, not events. The poller diffs
consecutive snapshots to recover what a live coach needs:

| Signal | How |
|---|---|
| Minutes on the pitch | `stats.minutes` per poll |
| **Substitutions** | minutes stop advancing while the match clock runs |
| Rolling team xG | xG accrued between two snapshots |
| Goal difference, match minute | fixtures endpoint |
| Bookings | per-fixture card stats |

Substitution detection needs **at least two polls** - on a cold start nobody can
yet be known to have been withdrawn.

### Measured accuracy cost

Only 13 of the 28 features survive a live FPL feed (all pass, spatial,
possession, pressure and duel data is unavailable). The cost was measured
before building - `python measure_live_ceiling.py`:

| Variant | Feat | ROC | PR-AUC | Top-3 |
|---|---|---|---|---|
| Full event data | 28 | 0.864 | 0.111 | **67.7%** |
| Live + involvement proxy | 19 | 0.856 | 0.098 | 60.6% |
| **Live core (deployed)** | **13** | **0.855** | **0.100** | **58.4%** |

Dropping 15 features costs ~1% of ROC-AUC but ~14% relative on top-3 ranking:
the survivors carry the population-level signal, while the lost ones did the
finer work of separating players *within* one team at one moment.

The 19-feature proxy variant scored no better than the 13-feature one, so the
poller deliberately does **not** reconstruct event-count proxies.

### What gets stored

```
data/live/gw{n}/
  timeline.parquet        one row per (poll, fixture, player):
                          minutes, xG, on/off pitch, booking, team state
  recommendations.jsonl   every recommendation set + the state that produced it
```

Keeping the recommendations means accuracy can be scored against what the real
coach subsequently did (`--evaluate`), not only against historical data.

### Replay a real match

```bash
python -m pipeline.replay
```

Walks a match forward in time, ranking players using only information available
at each minute, and compares against the coach's actual decisions.

### Fidelity note

Full-fidelity coaching (the 28-feature model) needs event-level data and runs
today via replay. Live 2026/27 coaching runs on the 13-feature model above.

## Project history

This repo previously tracked live World Cup 2026 matches via ESPN and
Sofascore/FotMob scrapers. Those sources were bot-blocked and their player
metrics stubbed, so the live path fell back to generated numbers. That data
layer was replaced by the FPL/FBref pipeline above.

The match-analysis modules from that system are retained and unwired
(`live_fitness_calculator`, `online_model_trainer`, `match_event_detector`,
`match_state_tracker`, `substitution_tracker`) - the fitness model becomes
usable again once real physical data is connected.
