# ⚽ FIFA Shadow Coach v3.1

**Agent-powered AI football analytics** — Real-time live match data from ESPN/Sofascore, player fitness tracking, and tactical recommendations via multi-agent orchestration.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![LangChain 1.2+](https://img.shields.io/badge/LangChain-1.2+-green.svg)](https://langchain.com/)
[![Redis](https://img.shields.io/badge/Redis-Required-orange.svg)](https://redis.io/)

---

## 🎯 What It Does

FIFA Shadow Coach is a **multi-agent real-time match analytics system** that uses orchestrated AI agents to analyze live football matches and provide data-driven substitution recommendations.

### Core Features

✅ **Live Match Simulation**
- Runs Monte Carlo trials per minute
- Forecasts win/draw/loss probabilities in real-time

✅ **Player Fatigue Detection**
- Exponential decay model (10-day recovery half-life)
- Tracks cumulative load per player
- Risk scoring: HIGH/MEDIUM/LOW fatigue levels
- Substitution recommendations based on energy state

✅ **Auto-Improving System**
- Post-match backpropagation: compares AI recommendations vs actual manager decisions
- Updates feature weights automatically
- Stored in `config/feature_weights.yaml` (version controlled)
- Learns from every match analyzed

✅ **Interactive Dashboard**
- Live score updates
- Squad fatigue matrix with color coding
- Win probability charts
- Tactical recommendations with confidence scores

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/harshul27/Fifalyst.git
cd Fifalyst

# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py

# Opens at http://localhost:8501
```

---

## 📋 Installation

### Prerequisites
- Python 3.11+
- pip or conda
- ~200 MB disk space for dependencies

### Setup

```bash
# Clone repository
git clone https://github.com/harshul27/Fifalyst.git
cd Fifalyst

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import streamlit, duckdb, pandas; print('All dependencies installed')"
```

---

## 🎮 Usage

### Start the Dashboard

```bash
streamlit run app.py
# Opens at http://localhost:8501
```

### Dashboard Features

1. **Sidebar: Match Configuration**
   - Select home and away teams
   - Choose simulation parameters

2. **Squad State & Fatigue**
   - Interactive table showing each player's energy level
   - Risk scoring (HIGH/MEDIUM/LOW)
   - Match count and intensity metrics

3. **Live Match Simulation**
   - Click "Stream Live" to run Monte Carlo trials
   - Real-time probability updates
   - Fatigue decay visualization

---

## 🏗️ Architecture

### System Design

```
┌─────────────────────────────────────────────────┐
│         Streamlit Frontend Dashboard            │
│  (Squad fatigue, live scores, recommendations)  │
└──────────────────┬──────────────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────▼───┐  ┌─────▼────┐  ┌─────▼────┐
│ Model  │  │ Pipeline │  │ Storage  │
│ (Monte │  │ (ETL +   │  │ (DuckDB) │
│ Carlo) │  │ Backprop)│  │          │
└────────┘  └──────────┘  └──────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Streamlit | Interactive dashboard |
| **Analytics** | NumPy + Pandas | Vectorized computation |
| **Database** | DuckDB | File-based, zero setup |
| **Scraping** | BeautifulSoup4 | Data collection |
| **Automation** | GitHub Actions | Daily pipeline runs |

---

## 🔧 Configuration

### Simulation Parameters (`config/sim_config.yaml`)

```yaml
simulation:
  n_simulations: 10000
  base_goal_intensity_lambda: 2.5
  tau_decay: 0.5
  min_pes_floor: 15.0
  max_pes_ceiling: 100.0

match:
  total_minutes: 90
  substitute_window_start: 45
  substitute_window_end: 85
  max_substitutions: 3

feature_weights:
  alpha_fatigue: 1.0
  alpha_intensity: 0.8
  alpha_recovery: 0.6
```

### Player Metadata (`config/player_metadata.yaml`)

Position-based baseline stamina and substitution thresholds:

```yaml
baseline_stamina:
  GK: 85.0
  CB: 90.0
  CM: 92.0
  CF: 88.0
  LW: 86.0
  # ...

substitution_thresholds:
  GK: 30.0
  CB: 35.0
  CM: 38.0
  CF: 36.0
  # ...
```

### Feature Weights (`config/feature_weights.yaml`)

**Auto-updated after each match** via backpropagation.

---

## 📊 How It Works

### Player Energy Score (PES)

Each player has an energy level [15-100] based on:

```
PES = 100 - Σ(strain_i * exp(-λ * days_ago_i))

where:
  strain_i = minutes_played_i * intensity_i / 90
  λ = ln(2) / 10 ≈ 0.0693 (10-day half-life)
```

**Example:**
- Fresh player: PES = 100.0
- After 90-min intense match (yesterday): PES ≈ 70-80
- After 90-min match (10 days ago): PES ≈ 92 (half decayed)

### Match Outcome Prediction

Monte Carlo simulation:

```python
# For each of N trials:
remaining_minutes = 90 - current_minute
home_lambda = 2.5 * (remaining_minutes/90) * (home_pes/100)
away_lambda = 2.5 * (remaining_minutes/90) * (away_pes/100)

home_goals ~ Poisson(home_lambda)
away_goals ~ Poisson(away_lambda)

if home_goals > away_goals: home_win += 1
elif home_goals == away_goals: draw += 1
else: away_win += 1

# Return percentages
```

### Auto-Improving Feedback Loop

After each match:

```
1. Get match outcome (actual result)
2. Compare vs AI recommendation
3. Calculate loss: how wrong was the prediction?
4. Backpropagate error into feature_weights
5. Update config/feature_weights.yaml (committed to Git)
6. Next match: use updated weights
```

---

## 💰 Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| **Database** | $0/month | DuckDB file-based, no server needed |
| **Dependencies** | $0/month | All open-source |
| **Total** | **$0/month** | 100% free to run locally |

---

## 📁 Project Structure

```
Fifalyst/
├── app.py                       # Streamlit frontend dashboard
├── model.py                     # Monte Carlo engine, player energy model
├── pipeline.py                  # ETL, feature engineering, backpropagation
├── requirements.txt             # Python dependencies
├── match_pipeline.yml           # GitHub Actions workflow
│
├── data/
│   └── database.duckdb          # DuckDB file-based database
│
├── fifa-shadow-coach/           # Packaged project
│   ├── src/
│   │   ├── app.py               # Streamlit app (packaged)
│   │   ├── model.py             # Monte Carlo engine (packaged)
│   │   ├── pipeline.py          # ETL pipeline (packaged)
│   │   └── __init__.py
│   ├── config/
│   │   ├── sim_config.yaml      # Simulation hyperparameters
│   │   ├── player_metadata.yaml # Player attributes by position
│   │   └── feature_weights.yaml # Model weights (auto-updated)
│   ├── .github/
│   │   └── workflows/
│   │       └── match_pipeline.yml
│   ├── data/
│   ├── tests/
│   ├── .gitignore
│   ├── QUICKSTART.md
│   ├── README.md
│   └── requirements.txt
│
└── README.md                    # This file
```

---

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

---

## 🤝 Contributing

Contributions are welcome! Areas we'd like help with:

- [ ] Additional player attributes (sprint speed, positional awareness)
- [ ] Integration with more football data APIs (StatsBomb, Wyscout, Understat)
- [ ] Machine learning model improvements (gradient boosting, neural networks)
- [ ] Performance optimizations
- [ ] Additional test coverage

**To contribute:**

```bash
# 1. Fork repository
# 2. Create feature branch
git checkout -b feature/my-feature

# 3. Make changes and add tests
# 4. Commit
git commit -m "feat: add my feature"

# 5. Push and create Pull Request
git push origin feature/my-feature
```

---

## 🙋 Support & Feedback

- **Issues:** [GitHub Issues](https://github.com/harshul27/Fifalyst/issues)
- **Discussions:** [GitHub Discussions](https://github.com/harshul27/Fifalyst/discussions)
- **Email:** harshul2705@gmail.com

---

## 🗺️ Roadmap

### Phase 1 (Current)
- ✅ Real-time match simulation
- ✅ Player fatigue tracking
- ✅ Auto-improving feedback loop
- ✅ Interactive Streamlit dashboard

### Phase 2 (Coming)
- [ ] Multi-league support (Premier League, La Liga, Serie A)
- [ ] Advanced fatigue metrics (sprint distance, acceleration, deceleration)
- [ ] Formation analysis
- [ ] Set-piece probability

### Phase 3 (Future)
- [ ] Mobile app
- [ ] Team collaboration features
- [ ] Historical match replay analysis

---

## 🎯 Key Metrics

- **Lines of Code:** ~1,200 (highly vectorized)
- **Dependencies:** 6 (minimal, well-maintained)
- **Startup Time:** <1 second
- **Simulation Time:** <100ms per 10k trials

---

## 👨‍💻 Authors

**Harshul Shah** (harshul2705@gmail.com)

---

## 🙏 Acknowledgments

- **Streamlit** team for the amazing dashboard framework
- **DuckDB** team for blazing-fast analytics database
- **NumPy/Pandas** for high-performance computation
- Football analytics community for inspiration

---

![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![Version](https://img.shields.io/badge/Version-3.1-green.svg)

---

**Star ⭐ this repo if you find it useful!**

---

<div align="center">

Made with ❤️ for football analytics

[⬆ Back to top](#-fifa-shadow-coach)

</div>
