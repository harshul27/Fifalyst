# FIFA Shadow Coach - Match Simulation & Player Fatigue Engine

Serverless, free-to-run auto-improving FIFA World Cup match simulation and player fatigue tracking system.

## Tech Stack
- **Backend**: Python 3.11, DuckDB, Pandas, NumPy
- **Frontend**: Streamlit
- **Orchestration**: GitHub Actions (daily cron)

## Quick Start

1. Install: `pip install -r requirements.txt`
2. Pipeline: `python src/pipeline.py`
3. Dashboard: `streamlit run src/app.py`

## Project Structure

```
fifa-shadow-coach/
├── .github/workflows/match_pipeline.yml
├── src/
│   ├── model.py          # Monte Carlo + PES
│   ├── pipeline.py       # ETL + feature engineering
│   └── app.py            # Streamlit dashboard
├── config/
│   ├── sim_config.yaml
│   ├── player_metadata.yaml
│   └── feature_weights.yaml
├── data/
│   └── .gitkeep
├── requirements.txt
└── README.md
```

## Key Components

**Player Energy Score (PES)**: Exponential decay with 10-day half-life (15-100 range)

**Monte Carlo**: 10k Poisson trials per match state for win probabilities

**Auto-Improve Loop**: Post-match backprop adjusts feature weights

## GitHub Actions

Daily cron (midnight UTC) runs pipeline + auto-commits changes.

## License

Open source.
