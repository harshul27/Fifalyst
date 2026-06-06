# FIFA RT Pred Eng - Project File Tree

```
fifa-shadow-coach/
├── .github/
│   └── workflows/
│       └── match_pipeline.yml          # Daily cron + manual trigger for pipeline
├── src/
│   ├── __init__.py
│   ├── pipeline.py                     # Main orchestration: fetch → simulate → backprop
│   ├── simulator.py                    # Monte Carlo engine (10k sims per match)
│   ├── player_fatigue.py               # Load management, strain tracking
│   ├── features.py                     # Feature extraction & vectorization
│   ├── backprop.py                     # Post-match error backprop into weights
│   ├── data_loader.py                  # Parquet I/O, DuckDB queries
│   └── utils.py                        # Helpers, validation, error handling
├── config/
│   ├── sim_config.yaml                 # Simulation hyperparams (n_sims, tau, weights)
│   ├── player_metadata.yaml            # Position mappings, baseline attributes
│   └── feature_weights.yaml            # Current model weights (updated post-match)
├── data/
│   ├── matches/
│   │   ├── raw/
│   │   │   └── matches_2024.parquet    # Raw match data (scores, events, timing)
│   │   └── processed/
│   │       └── matches_features.parquet # Extracted features per match
│   ├── players/
│   │   ├── base_stats.parquet          # Baseline player attributes (pace, stamina)
│   │   └── fatigue_tracking.parquet    # Per-player cumulative load history
│   ├── simulations/
│   │   └── sim_results_{date}.parquet  # 10k Monte Carlo outputs per match
│   └── models/
│       └── feature_matrix.parquet      # Precomputed feature-to-outcome matrix
├── tests/
│   ├── __init__.py
│   ├── test_simulator.py               # Unit tests for Monte Carlo
│   ├── test_fatigue.py                 # Fatigue logic validation
│   └── test_backprop.py                # Backprop correctness checks
├── .gitignore                          # Exclude venv/, __pycache__, .DS_Store
├── requirements.txt                    # Python dependencies (pinned)
├── README.md                           # Project overview & quick-start guide
└── run_locally.py                      # Local testing harness (no GitHub Actions)
```

## Key Design Decisions

| Layer | File(s) | Purpose |
|-------|---------|---------|
| **Orchestration** | `pipeline.py` | Stateless entry point; coordinates loader → simulator → backprop |
| **Simulation** | `simulator.py` | Vectorized Monte Carlo; outputs 10k tactical scenarios per match |
| **Fatigue** | `player_fatigue.py` | Tracks cumulative strain; gates substitution recommendations |
| **Features** | `features.py` | Extracts match state, player positions, defensive/attacking intensity |
| **Learning** | `backprop.py` | Compares real vs. recommended decisions; updates `feature_weights.yaml` |
| **Data I/O** | `data_loader.py` | DuckDB wrapper for Parquet ingestion; lazy queries only |
| **Config** | `config/*.yaml` | Single source of truth for hyperparams; versioned in Git |

## Parquet Asset Locations

All `.parquet` files live in `data/` and are committed to Git (compressed, ~MB-scale):
- **Raw match metrics** → `data/matches/raw/`
- **Processed features** → `data/matches/processed/`
- **Player attributes** → `data/players/`
- **Simulation outputs** → `data/simulations/` (archived per date)
- **Backprop matrix** → `data/models/`

## GitHub Actions Artifacts

The workflow (`match_pipeline.yml`) commits back to `main`:
- Any modified `.parquet` files
- Updated `config/feature_weights.yaml` (after backprop)
- Timestamped logs (optional)
