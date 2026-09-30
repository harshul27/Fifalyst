# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FIFA World Cup 2026 live match analytics ("FIFA Shadow Coach"): pulls live matches from ESPN, estimates per-player in-match fitness, and suggests substitutions in a Streamlit dashboard.

**README.md and SETUP.md are out of date.** They describe files that are gone (`app.py`, `model.py`, `pipeline.py`, `verify_agents.py`, `agents/`, `config/*.yaml`), plus a LangChain multi-agent/Redis design that was replaced by a plain async pipeline ("Phase 6: consolidate to production architecture"). `config.yaml`, `requirements_multiagent.txt`, `deployment/` (Postgres/Weaviate/Prometheus/Grafana, plus a `deploy.sh` that points to a `docker-compose.prod.yml` that doesn't exist) and `.env.example` come from that older design. None of the running code reads them.

## Commands

```bash
pip install -r requirements.txt
pip install crawl4ai            # needed by pipeline/live_web_scraper.py, missing from requirements.txt

streamlit run world_cup_app.py  # dashboard at http://localhost:8501
python orchestrator.py          # run one live cycle, print the JSON result
python test_e2e.py              # end-to-end check against the live ESPN API (script, not pytest)
```

Each module in `pipeline/` and `models/` has an `async def main()` demo under `if __name__ == "__main__"`, so you can smoke-test one module on its own, e.g. `python -m pipeline.live_fitness_calculator`.

Tests: `tests/test_orchestration.py` is mostly commented-out stubs for the old agent design. `tests/test_dashboard.py` imports `dashboard.app`, which doesn't exist. `test_e2e.py` is the only test that exercises the current code. For a single pytest test: `pytest tests/test_dashboard.py::test_wc_teams_filter`. There's no lint or format config.

## Architecture

Data flow for each dashboard load:

`world_cup_app.py` → `orchestrator.get_orchestrator()` (a module-level singleton) → `LiveMatchOrchestrator.run_cycle()`. Streamlit caches the result for 5 minutes with `@st.cache_data(ttl=300)` and runs the async cycle on a new event loop each time.

`run_cycle()`:
1. `LiveMetricsFetcher.fetch_live_matches()` calls the ESPN public scoreboard (`site.api.espn.com/.../fifa.world/scoreboard`). The call is synchronous `requests`, wrapped in `run_in_executor`. It drops finished (`post`) games. The orchestrator then keeps only matches where both teams are in its hardcoded `WC_TEAMS` set.
2. Each match goes through `process_match()` concurrently via `asyncio.gather`:
   - `MatchStateTracker.update_match_state()` maps minute to a state (SCHEDULED / LIVE_1ST / HALFTIME / LIVE_2ND / FINISHED). State lives in memory only. The `.cache/match_states.json` path is never written. The substitution limit is 5.
   - Baseline fitness and running load are **deterministic placeholders computed from `hash(player_id)`**. When `minute > 0`, `LiveWebDataAggregator` (crawl4ai scraping of Sofascore, falling back to FotMob) is tried first, and `distance_km` is converted to running load. Scraper failures are swallowed and fall back to the placeholder.
   - `LiveFitnessCalculator.calculate_fitness()` is rule-based: fatigue ∝ minute/90, a +5 penalty above 110% load, and a position multiplier (GK/DEF/MID/ATT). Status buckets are PEAK/HOT/FAIR/CRITICAL.
   - `_generate_recommendations()` runs only from minute 30 on. It pairs a tired player (fitness < 50) with a fresh one (fitness > 80, `minutes_on == 0`) and returns the top 3 by confidence (0.60–0.95).
3. The result is `{'matches': [...], 'count', 'timestamp'}`. Each match dict carries `home_fitness`, `away_fitness` and `recommendations`, which the dashboard renders directly.

Behaviour to know about before changing things:
- Every stage catches its own exceptions and returns an empty value (`[]`, `{}`, `{'home': [], 'away': []}`), so failures show up only in logs, never as errors.
- `process_match` sets `minutes_on = minute` for every player. That means the "fresh bench player" condition (`minutes_on == 0`) can never be met during play, so live recommendations currently come back empty.
- `models/` isn't wired into the live path. `FitnessPredictor` returns random values around 75, and `phase4_pipeline.py` imports a `trainer` module that doesn't exist. `pipeline/player_live_metrics.py` is also unused.
- `data/` holds prebuilt artifacts (parquet/CSV/JSON squads, PES tables, `database.duckdb`) that the current live pipeline doesn't read.
- `__pycache__/`, `*.log`, and `dump.rdb` are committed, and there's no `.gitignore`.
