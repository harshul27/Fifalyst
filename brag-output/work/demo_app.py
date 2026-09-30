"""Runs the real world_cup_app.py with a sample live match fed through the real
LiveFitnessCalculator and _generate_recommendations (ESPN/scraper stubbed)."""
import sys, types, asyncio, os
from datetime import datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
stub = types.ModuleType('pipeline.live_web_scraper')
class LiveWebDataAggregator:
    async def fetch_live_player_metrics(self, *a): return {'home': [], 'away': []}
stub.LiveWebDataAggregator = LiveWebDataAggregator
sys.modules['pipeline.live_web_scraper'] = stub
import streamlit as st
st.cache_data = lambda *a, **k: (lambda f: f)
import orchestrator

M = int(st.query_params.get('m', 34))
home = [('Goalkeeper #1','GK',90),('Defender #4','DEF',88),('Midfielder #8','MID',86),('Midfielder #10','MID',84),('Winger #11','ATT',83),('Striker #9','ATT',80)]
away = [('Goalkeeper #13','GK',89),('Defender #3','DEF',87),('Midfielder #6','MID',85),('Midfielder #16','MID',84),('Winger #7','ATT',82),('Striker #22','ATT',81)]
BENCH = {'home': ('Forward #19','ATT',89), 'away': ('Forward #20','ATT',86)}

class DemoOrch(orchestrator.LiveMatchOrchestrator):
    async def run_cycle(self):
        st_ = self.state_tracker.update_match_state('arg_mex','Argentina','Mexico',M,1,0,[],[])
        out = {}
        for side, xi in (('home', home), ('away', away)):
            players = [{'player_id': n, 'name': n, 'position': p, 'baseline_fitness': b} for n,p,b in xi]
            b = BENCH[side]
            bench = [{'player_id': b[0], 'name': b[0], 'position': b[1], 'baseline_fitness': b[2]}]
            load = [{'player_id': n, 'running_load_pct': 115 if p=='ATT' else 95} for n,p,_ in xi]
            fl = await self.fitness_calc.calculate_fitness(players + bench, load, M)
            out[side] = [{'name': f.name, 'player_id': f.player_id, 'fitness': float(f.current_fitness),
                          'fatigue_pct': float(f.fatigue_pct), 'status': f.fatigue_status,
                          'minutes_on': 0 if f.player_id == b[0] else M} for f in fl]
        recs = self._generate_recommendations(st_, out, 1, 0)
        match = {'match_id':'arg_mex','status':'LIVE','minute':M,'score':'1-0','home_team':'Argentina','away_team':'Mexico',
                 'home_fitness':out['home'],'away_fitness':out['away'],'recommendations':recs}
        return {'matches':[match],'count':1,'timestamp':'2026-06-27T21:34:12'}

orchestrator.get_orchestrator = lambda: DemoOrch()
sys.modules['orchestrator'] = orchestrator
exec(open(os.path.join(ROOT, 'world_cup_app.py')).read())
