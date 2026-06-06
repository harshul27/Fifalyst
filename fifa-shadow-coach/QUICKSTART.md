# Quick Start Guide - FIFA Shadow Coach

## Prerequisites
- Python 3.11+
- pip

## Setup

```bash
cd fifa-shadow-coach
pip install -r requirements.txt
python src/pipeline.py
```

## Run Dashboard

```bash
streamlit run src/app.py
```

Opens at: http://localhost:8501

## Features

- **Sidebar**: Select Home/Away teams
- **Left Column**: Squad energy state (9 players) with fatigue color-coding
- **Right Column**: Live match simulation 60'-90' with real-time win probability chart

## Troubleshooting

No parquet file? Run: `python src/pipeline.py`
Port 8501 busy? Use: `streamlit run src/app.py --server.port 8502`
