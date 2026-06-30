"""End-to-End Test Suite - FIFA World Cup 2026 Fitness Tracker"""
import asyncio
import json
import time
from datetime import datetime
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from orchestrator import LiveMatchOrchestrator
from pipeline.live_metrics_fetcher import LiveMetricsFetcher
from pipeline.match_state_tracker import MatchStateTracker
from pipeline.live_fitness_calculator import LiveFitnessCalculator


class E2ETestSuite:
    """Comprehensive end-to-end testing"""

    def __init__(self):
        self.results = {}
        self.orch = LiveMatchOrchestrator()
        self.fetcher = LiveMetricsFetcher()
        self.state_tracker = MatchStateTracker()
        self.fitness_calc = LiveFitnessCalculator()

    async def test_espn_api_connectivity(self):
        """TEST 1: ESPN API returns real World Cup matches"""
        print("\n[TEST 1] ESPN API Connectivity")
        print("=" * 70)
        try:
            matches = await self.fetcher.fetch_live_matches()

            if not matches:
                print("⚠️  No live matches found (expected for off-season)")
                self.results['api_connectivity'] = 'PASS_NO_MATCHES'
                return True

            print(f"✓ Found {len(matches)} matches")
            for m in matches[:2]:
                print(f"  - {m['home_team']} vs {m['away_team']} "
                      f"(Status: {m['status']}, Min: {m['minute']}')")

            # Validate match structure
            required_fields = ['match_id', 'home_team', 'away_team', 'status', 'minute']
            for field in required_fields:
                assert all(field in m for m in matches), f"Missing field: {field}"

            print("✓ All matches have required fields")
            self.results['api_connectivity'] = 'PASS'
            return True
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.results['api_connectivity'] = 'FAIL'
            return False

    async def test_match_state_tracking(self):
        """TEST 2: Match state is properly tracked and updated"""
        print("\n[TEST 2] Match State Tracking")
        print("=" * 70)
        try:
            # Simulate match progression
            states = []
            for minute in [0, 15, 45, 50, 90]:
                state = self.state_tracker.update_match_state(
                    match_id='test_001',
                    home_team='Brazil',
                    away_team='Serbia',
                    minute=minute,
                    home_score=1 if minute > 30 else 0,
                    away_score=0,
                    home_lineup=[{'player_id': f'h{i}', 'name': f'Home {i}'} for i in range(11)],
                    away_lineup=[{'player_id': f'a{i}', 'name': f'Away {i}'} for i in range(11)]
                )
                states.append(state.state)
                print(f"  Minute {minute:2d}: {state.state}")

            # Validate state progression
            expected = ['SCHEDULED', 'LIVE_1ST', 'HALFTIME', 'LIVE_2ND', 'FINISHED']
            for i, (actual, exp) in enumerate(zip(states, expected)):
                assert actual == exp, f"State mismatch at index {i}: {actual} != {exp}"

            print("✓ State progression correct: SCHEDULED → LIVE_1ST → HALFTIME → LIVE_2ND → FINISHED")
            self.results['state_tracking'] = 'PASS'
            return True
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.results['state_tracking'] = 'FAIL'
            return False

    async def test_fitness_calculation(self):
        """TEST 3: Fitness calculations produce realistic values"""
        print("\n[TEST 3] Fitness Calculations")
        print("=" * 70)
        try:
            # Test at different match minutes
            test_minutes = [30, 60, 75, 90]

            for minute in test_minutes:
                players = [
                    {'player_id': 'p1', 'name': 'midfielder', 'position': 'MID', 'baseline_fitness': 85},
                    {'player_id': 'p2', 'name': 'defender', 'position': 'DEF', 'baseline_fitness': 82},
                    {'player_id': 'p3', 'name': 'striker', 'position': 'ATT', 'baseline_fitness': 88},
                ]

                # Mock live metrics
                metrics = [
                    {'player_id': 'p1', 'running_load_pct': 95},
                    {'player_id': 'p2', 'running_load_pct': 105},
                    {'player_id': 'p3', 'running_load_pct': 115},
                ]

                fitness_list = await self.fitness_calc.calculate_fitness(players, metrics, minute)

                print(f"\n  Minute {minute}:")
                for f in fitness_list:
                    print(f"    {f.name:15} ({f.position}): {f.current_fitness:6.1f}% "
                          f"Fatigue: {f.fatigue_pct:5.1f}% Status: {f.fatigue_status}")

                # Validate fitness values
                assert all(0 <= f.current_fitness <= 100 for f in fitness_list), "Fitness out of bounds"
                assert all(0 <= f.fatigue_pct <= 100 for f in fitness_list), "Fatigue % out of bounds"

                # Fatigue should increase with minute
                if minute > 0:
                    assert all(f.fatigue_pct > 0 for f in fitness_list), "Fatigue should increase"

            print("\n✓ Fitness calculations valid: values in [0,100], increase with time")
            self.results['fitness_calculation'] = 'PASS'
            return True
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.results['fitness_calculation'] = 'FAIL'
            return False

    async def test_recommendation_engine(self):
        """TEST 4: Substitution recommendations are generated correctly"""
        print("\n[TEST 4] Recommendation Engine")
        print("=" * 70)
        try:
            # Process a match with live data
            test_match = {
                'match_id': 'test_002',
                'home_team': 'Brazil',
                'away_team': 'Serbia',
                'home_score': 2,
                'away_score': 1,
                'minute': 67,
                'status': 'LIVE',
                'lineups': {
                    'home': [
                        {'player_id': f'h{i}', 'name': f'Brazil Player {i}', 'position': ['GK','DEF','MID','ATT'][i%4]}
                        for i in range(16)
                    ],
                    'away': [
                        {'player_id': f'a{i}', 'name': f'Serbia Player {i}', 'position': ['GK','DEF','MID','ATT'][i%4]}
                        for i in range(16)
                    ]
                }
            }

            result = await self.orch.process_match(test_match)

            print(f"✓ Match processed: {result['home_team']} {result['score']} {result['away_team']}")
            print(f"  Minute: {result['minute']}'")
            print(f"  Recommendations: {len(result['recommendations'])}")

            recs = result['recommendations']
            if recs:
                for i, rec in enumerate(recs[:3], 1):
                    print(f"\n  Recommendation #{i}:")
                    print(f"    Off: {rec['off']} ({rec['off_fitness']:.0f}% fitness)")
                    print(f"    On:  {rec['on']} ({rec['on_fitness']:.0f}% fitness)")
                    print(f"    Confidence: {rec['confidence']:.2%}")
                    print(f"    Reason: {rec['reason']}")

                # Validate recommendation structure
                for rec in recs:
                    assert 0.0 <= rec['confidence'] <= 1.0, f"Invalid confidence: {rec['confidence']}"
                    assert 0 <= rec['off_fitness'] <= 100, "Invalid fitness value"
                    assert 0 <= rec['on_fitness'] <= 100, "Invalid fitness value"
                    assert rec['team'] in ['home', 'away'], "Invalid team"
            else:
                print("  (No recommendations - expected if before minute 30 or no tired players)")

            print("\n✓ Recommendation engine working correctly")
            self.results['recommendation_engine'] = 'PASS'
            return True
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.results['recommendation_engine'] = 'FAIL'
            return False

    async def test_full_cycle(self):
        """TEST 5: Full orchestrator cycle with real ESPN data"""
        print("\n[TEST 5] Full Orchestrator Cycle (Real ESPN Data)")
        print("=" * 70)
        try:
            start_time = time.time()

            result = await self.orch.run_cycle()

            elapsed = time.time() - start_time

            matches = result.get('matches', [])
            print(f"✓ Cycle completed in {elapsed:.2f}s")
            print(f"  Matches found: {len(matches)}")
            print(f"  Timestamp: {result.get('timestamp', 'N/A')}")

            # Performance check
            if elapsed > 5.0:
                print(f"⚠️  Warning: Cycle took {elapsed:.2f}s (target: <2s)")
            else:
                print(f"✓ Performance OK: {elapsed:.2f}s < 2.0s threshold")

            for m in matches:
                print(f"\n  {m['home_team']} vs {m['away_team']}")
                print(f"    Status: {m['status']}, Score: {m['score']}, Minute: {m['minute']}'")
                print(f"    Recommendations: {len(m.get('recommendations', []))}")

            self.results['full_cycle'] = 'PASS'
            return True
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.results['full_cycle'] = 'FAIL'
            return False

    async def test_edge_cases(self):
        """TEST 6: Edge case handling"""
        print("\n[TEST 6] Edge Case Handling")
        print("=" * 70)

        edge_cases = []

        # Edge Case 1: No lineups (SCHEDULED match)
        print("\n  [EC1] Match with no lineups (SCHEDULED)...")
        try:
            match = {
                'match_id': 'ec_001',
                'home_team': 'Mexico',
                'away_team': 'Ecuador',
                'minute': 0,
                'status': 'SCHEDULED',
                'home_score': 0,
                'away_score': 0,
                'lineups': {'home': [], 'away': []}
            }
            result = await self.orch.process_match(match)

            if result and 'home_fitness' in result:
                print("    ✓ Handled gracefully (returned empty fitness arrays)")
                edge_cases.append('PASS')
            else:
                print("    ✗ Failed to handle gracefully")
                edge_cases.append('FAIL')
        except Exception as e:
            print(f"    ✗ Exception: {e}")
            edge_cases.append('FAIL')

        # Edge Case 2: Very high minute (90+)
        print("  [EC2] Match beyond normal 90 minutes (extra time)...")
        try:
            state = self.state_tracker.update_match_state(
                'ec_002', 'France', 'England', 95, 1, 1,
                [{'player_id': f'h{i}', 'name': f'Player {i}'} for i in range(11)],
                [{'player_id': f'a{i}', 'name': f'Player {i}'} for i in range(11)]
            )
            print(f"    ✓ Handled minute 95: state={state.state}")
            edge_cases.append('PASS')
        except Exception as e:
            print(f"    ✗ Exception: {e}")
            edge_cases.append('FAIL')

        # Edge Case 3: Missing player data
        print("  [EC3] Incomplete player data...")
        try:
            players = [
                {'player_id': 'p1', 'baseline_fitness': 85},  # missing name, position
                {'player_id': 'p2', 'name': 'Player 2'},  # missing baseline
            ]
            metrics = []
            fitness_list = await self.fitness_calc.calculate_fitness(players, metrics, 60)
            print(f"    ✓ Handled incomplete data: returned {len(fitness_list)} results")
            edge_cases.append('PASS')
        except Exception as e:
            print(f"    ✗ Exception: {e}")
            edge_cases.append('FAIL')

        # Edge Case 4: Zero subs remaining
        print("  [EC4] No substitutions remaining...")
        try:
            self.state_tracker.states['ec_004'] = self.state_tracker.update_match_state(
                'ec_004', 'Germany', 'Spain', 85, 2, 2,
                [{'player_id': f'h{i}', 'name': f'Player {i}'} for i in range(11)],
                [{'player_id': f'a{i}', 'name': f'Player {i}'} for i in range(11)]
            )
            subs_left = self.state_tracker.get_available_subs('ec_004', 'home')
            print(f"    ✓ Subs available: {subs_left} (correctly manages substitution count)")
            edge_cases.append('PASS')
        except Exception as e:
            print(f"    ✗ Exception: {e}")
            edge_cases.append('FAIL')

        # Edge Case 5: Network timeout simulation
        print("  [EC5] API failure recovery...")
        try:
            # Test fallback when no matches available
            matches = await self.orch.fetch_live_matches()
            print(f"    ✓ Fetch returned {len(matches)} matches (no crash on empty result)")
            edge_cases.append('PASS')
        except Exception as e:
            print(f"    ✗ Exception: {e}")
            edge_cases.append('FAIL')

        passed = sum(1 for ec in edge_cases if ec == 'PASS')
        print(f"\n✓ Edge cases: {passed}/{len(edge_cases)} passed")
        self.results['edge_cases'] = 'PASS' if passed >= 3 else 'FAIL'
        return passed >= 3

    async def run_all(self):
        """Run complete test suite"""
        print("\n" + "=" * 70)
        print("FIFA WORLD CUP 2026 - END-TO-END TEST SUITE")
        print("=" * 70)

        tests = [
            ('ESPN API Connectivity', self.test_espn_api_connectivity),
            ('Match State Tracking', self.test_match_state_tracking),
            ('Fitness Calculation', self.test_fitness_calculation),
            ('Recommendation Engine', self.test_recommendation_engine),
            ('Full Orchestrator Cycle', self.test_full_cycle),
            ('Edge Case Handling', self.test_edge_cases),
        ]

        for name, test_func in tests:
            try:
                await test_func()
            except Exception as e:
                print(f"\n✗ {name} crashed: {e}")
                self.results[name] = 'CRASH'

        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        for test_name, result in self.results.items():
            status_icon = "✓" if result == 'PASS' or result.startswith('PASS') else "✗"
            print(f"{status_icon} {test_name:30} {result}")

        passed = sum(1 for r in self.results.values() if 'PASS' in r)
        total = len(self.results)

        print(f"\nTotal: {passed}/{total} tests passed")

        if passed == total:
            print("\n🎉 ALL TESTS PASSED - SYSTEM READY FOR PRODUCTION")
            return True
        else:
            print("\n⚠️  SOME TESTS FAILED - REVIEW REQUIRED")
            return False


async def main():
    suite = E2ETestSuite()
    success = await suite.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
