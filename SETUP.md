# FIFA Shadow Coach - Agent-Powered Setup

**Version 3.1** - Real-time match analytics using multi-agent orchestration

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
pip install langchain-anthropic
```

### 2. Verify System

```bash
python verify_agents.py
```

### 3. Start Orchestrator (Terminal 1)

The orchestrator runs continuously, fetching live data and populating Redis:

```bash
python pipeline.py orchestrator
```

You should see:
```
[INFO] DataCollectionAgent: Starting data collection
[INFO] FitnessModelAgent: Computing fitness...
[INFO] LiveMatchAgent: Tracking match...
```

### 4. Start Dashboard (Terminal 2)

```bash
streamlit run app.py
```

Opens at: `http://localhost:8501`

## Architecture

### Agents (Background Process)

Running in the orchestrator loop:
1. **DataCollectionAgent** → Fetches ESPN/Sofascore match data
2. **FitnessModelAgent** → Computes player fitness scores
3. **LiveMatchAgent** → Tracks match state and lineups
4. **RecommendationEngineAgent** → Generates substitution recommendations
5. **FeedbackAgent** → Post-match analysis and learning

Data flows through Redis for inter-agent communication.

### Dashboard (Streamlit)

- Real-time match scoreboard
- Live squad fitness visualization
- Player-by-player fitness matrix
- Substitution recommendations (when available)
- Match simulation (60' → 90')

## Data Flow

```
ESPN/Sofascore APIs
        ↓
[DataCollectionAgent] → Redis
        ↓
[FitnessModelAgent, LiveMatchAgent] (parallel)
        ↓
[RecommendationEngineAgent]
        ↓
Dashboard queries Redis for live data
```

## Requirements

- Python 3.11+
- Redis (local: `redis-server`)
- API keys: None required (ESPN/Sofascore are public)

## Troubleshooting

**"Redis not available"**
- Install Redis: `brew install redis` (macOS) or `choco install redis` (Windows)
- Run: `redis-server`

**"Orchestrator not found"**
- Check: `python pipeline.py validate`
- Verify imports: `python verify_agents.py`

**"No matches appearing"**
- Orchestrator needs 5-10 seconds to fetch data on first run
- Check Redis: `redis-cli KEYS "fifa:match:*"`

## File Structure

```
fifa-shadow-coach-v2/
├── app.py                    # Streamlit dashboard
├── pipeline.py               # ETL & orchestration
├── orchestrator.py           # Multi-agent coordinator
├── agents/
│   ├── base_agent.py         # Base class (langchain 1.2+)
│   ├── data_collection_agent.py
│   ├── fitness_model_agent.py
│   ├── live_match_agent.py
│   ├── recommendation_engine_agent.py
│   └── feedback_agent.py
├── model.py                  # Monte Carlo simulation
├── requirements.txt
├── verify_agents.py          # System verification
└── data/
    └── database.duckdb      # Historical data storage
```

## Environment Variables

Create `.env` if needed:
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
ANTHROPIC_API_KEY=<your-key>  # Optional, uses system default if available
```

## Next Steps

- [ ] Run `verify_agents.py` to check system
- [ ] Start orchestrator in one terminal
- [ ] Open dashboard in another terminal
- [ ] Check data flows in Redis: `redis-cli KEYS "*"`
- [ ] Monitor logs for agent activity

## Support

For issues, check:
1. Redis is running: `redis-cli ping`
2. Agents can import: `python -c "from orchestrator import MasterOrchestrator"`
3. Dependencies are installed: `pip list | grep langchain`
