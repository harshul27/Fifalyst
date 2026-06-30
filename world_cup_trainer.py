"""
World Cup 2026 PES Model Trainer
Trains substitution recommendation model exclusively on 48 World Cup teams
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

from world_cup_data_loader import WorldCupDataLoader


class WorldCupTrainer:
    """Train PES model for World Cup 2026 teams only"""

    def __init__(self, data_dir: str = "data/world_cup_2026"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.loader = WorldCupDataLoader(data_dir)

    def compute_team_form(self, team_matches_df: pd.DataFrame) -> dict:
        """
        Compute team form metrics from recent matches
        """
        if team_matches_df.empty:
            return {
                'matches_played': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'goals_for': 0,
                'goals_against': 0,
                'goal_difference': 0,
                'win_rate': 0,
            }

        goals_for = team_matches_df['goals_for'].sum()
        goals_against = team_matches_df['goals_against'].sum()

        matches = len(team_matches_df)
        wins = (team_matches_df['result'] == 'W').sum() if 'result' in team_matches_df.columns else 0
        draws = (team_matches_df['result'] == 'D').sum() if 'result' in team_matches_df.columns else 0
        losses = (team_matches_df['result'] == 'L').sum() if 'result' in team_matches_df.columns else 0

        return {
            'matches_played': matches,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'goals_for': goals_for,
            'goals_against': goals_against,
            'goal_difference': goals_for - goals_against,
            'win_rate': (wins / matches * 100) if matches > 0 else 0,
        }

    def compute_world_cup_team_pes(self, player_pes_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute comprehensive PES for each World Cup team
        Uses player quality, squad depth, and position distribution
        """
        print("\nComputing World Cup Team PES...")

        team_pes_data = []

        for team in self.loader.teams:
            team_players = player_pes_df[player_pes_df['team'] == team]

            if len(team_players) < 5:  # Skip if insufficient data
                continue

            # Sort by PES descending
            sorted_players = team_players.sort_values('pes', ascending=False)

            # Top 11 (starting lineup)
            top_11 = sorted_players.head(11)
            top_11_pes = top_11['pes'].mean()

            # Bench (players 12-18)
            bench = sorted_players.iloc[11:18]
            bench_pes = bench['pes'].mean() if len(bench) > 0 else 0

            # Squad depth (total players available)
            squad_size = len(team_players)
            depth_score = min(20, (squad_size - 11) * 2)  # Bonus for depth

            # Position distribution
            positions = {}
            for pos in ['GK', 'CB', 'LB', 'RB', 'RM', 'LM', 'CM', 'OM', 'ST', 'LW', 'RW']:
                pos_count = len(team_players[team_players['position'].str.contains(pos, case=False, na=False)])
                positions[pos] = pos_count

            # Balance score (having players in all positions)
            filled_positions = sum(1 for count in positions.values() if count > 0)
            balance_score = min(10, filled_positions)

            # Peak players (count of PES > 80)
            peak_count = len(sorted_players[sorted_players['pes'] > 80])
            elite_factor = peak_count * 1.5

            # Calculate final team PES
            base_pes = 75
            player_quality = top_11_pes - 75  # Difference from baseline
            team_pes = base_pes + (player_quality * 0.7) + (depth_score * 0.3) + (balance_score * 0.2)
            team_pes = np.clip(team_pes, 40, 100)

            # Determine status
            if team_pes > 82:
                status = 'ELITE'
            elif team_pes > 75:
                status = 'STRONG'
            elif team_pes > 68:
                status = 'COMPETITIVE'
            elif team_pes > 60:
                status = 'DEVELOPING'
            else:
                status = 'STRUGGLING'

            team_pes_data.append({
                'team': team,
                'current_pes': round(team_pes, 1),
                'top_11_pes': round(top_11_pes, 1),
                'bench_pes': round(bench_pes, 1),
                'squad_size': squad_size,
                'elite_players': peak_count,
                'squad_depth': round(depth_score, 1),
                'position_balance': filled_positions,
                'status': status,
            })

        team_pes_df = pd.DataFrame(team_pes_data).sort_values('current_pes', ascending=False)
        print(f"  Computed PES for {len(team_pes_df)} World Cup teams")
        print(f"  PES Range: {team_pes_df['current_pes'].min():.1f} - {team_pes_df['current_pes'].max():.1f}")

        return team_pes_df

    def create_squad_profiles(self, player_pes_df: pd.DataFrame, team_pes_df: pd.DataFrame) -> dict:
        """
        Create detailed squad profiles for each World Cup team
        Organized by position with player PES scores
        """
        print("\nCreating squad profiles...")

        squad_profiles = {}

        for _, team_row in team_pes_df.iterrows():
            team = team_row['team']
            team_players = player_pes_df[player_pes_df['team'] == team].sort_values('pes', ascending=False)

            positions = {
                'GK': [],
                'DEF': [],
                'MID': [],
                'ATT': [],
                'BENCH': []
            }

            # Categorize players
            for idx, (_, player) in enumerate(team_players.iterrows()):
                player_data = {
                    'name': player['player_name'],
                    'position': player['position'],
                    'pes': player['pes'],
                    'appearances': int(player.get('appearances', 0)),
                    'goals': int(player.get('goals', 0)),
                    'rating': float(player.get('rating', 7)),
                }

                if idx < 11:  # Starting XI
                    pos = str(player.get('position', 'MID')).upper()
                    if 'GK' in pos:
                        positions['GK'].append(player_data)
                    elif any(x in pos for x in ['CB', 'LB', 'RB']):
                        positions['DEF'].append(player_data)
                    elif any(x in pos for x in ['CM', 'RM', 'LM']):
                        positions['MID'].append(player_data)
                    else:
                        positions['ATT'].append(player_data)
                else:  # Bench
                    positions['BENCH'].append(player_data)

            squad_profiles[team] = {
                'team_pes': team_row['current_pes'],
                'status': team_row['status'],
                'squad_size': team_row['squad_size'],
                'positions': positions,
            }

        print(f"  Created profiles for {len(squad_profiles)} teams")
        return squad_profiles

    def print_training_report(self, team_pes_df: pd.DataFrame, squad_profiles: dict):
        """Print comprehensive training report"""

        print("\n" + "="*80)
        print("WORLD CUP 2026 TRAINING REPORT")
        print("="*80)

        print("\nELITE TEAMS (PES > 82):")
        elite = team_pes_df[team_pes_df['current_pes'] > 82]
        for idx, row in elite.iterrows():
            print(f"  {row['team']:20} PES: {row['current_pes']:5.1f} | Elite Players: {row['elite_players']} | Squad: {row['squad_size']}")

        print("\nSTRONG TEAMS (75-82):")
        strong = team_pes_df[(team_pes_df['current_pes'] > 75) & (team_pes_df['current_pes'] <= 82)]
        for idx, row in strong.iterrows():
            print(f"  {row['team']:20} PES: {row['current_pes']:5.1f} | Elite Players: {row['elite_players']} | Squad: {row['squad_size']}")

        print("\nCOMPETITIVE TEAMS (68-75):")
        competitive = team_pes_df[(team_pes_df['current_pes'] > 68) & (team_pes_df['current_pes'] <= 75)]
        for idx, row in competitive.iterrows():
            print(f"  {row['team']:20} PES: {row['current_pes']:5.1f} | Elite Players: {row['elite_players']} | Squad: {row['squad_size']}")

        print("\nDEVELOPING TEAMS (< 68):")
        developing = team_pes_df[team_pes_df['current_pes'] <= 68]
        for idx, row in developing.iterrows():
            print(f"  {row['team']:20} PES: {row['current_pes']:5.1f} | Elite Players: {row['elite_players']} | Squad: {row['squad_size']}")

        print("\nKEY STATISTICS:")
        print(f"  Total Teams: {len(team_pes_df)}")
        print(f"  Mean Team PES: {team_pes_df['current_pes'].mean():.2f}")
        print(f"  Std Dev: {team_pes_df['current_pes'].std():.2f}")
        print(f"  Range: {team_pes_df['current_pes'].min():.1f} - {team_pes_df['current_pes'].max():.1f}")
        print(f"  Total Players: {sum(s['squad_size'] for s in squad_profiles.values())}")
        print(f"  Avg Squad Size: {np.mean([s['squad_size'] for s in squad_profiles.values()]):.0f}")

        print("\nTOP 5 TOURNAMENT FAVORITES:")
        for idx, (_, row) in enumerate(team_pes_df.head(5).iterrows(), 1):
            print(f"  {idx}. {row['team']:20} ({row['current_pes']:.1f}) - {row['status']}")

        print("\n" + "="*80)

    def save_training_artifacts(self, team_pes_df: pd.DataFrame, squad_profiles: dict,
                                player_pes_df: pd.DataFrame):
        """Save all training artifacts"""

        print("\nSaving training artifacts...")

        # Team PES
        team_file = self.data_dir / "world_cup_2026_teams_trained.parquet"
        team_pes_df.to_parquet(str(team_file), index=False)
        print(f"  Teams: {team_file}")

        # Player PES
        player_file = self.data_dir / "world_cup_2026_players_trained.parquet"
        player_pes_df.to_parquet(str(player_file), index=False)
        print(f"  Players: {player_file}")

        # Squad profiles (JSON)
        import json
        profiles_file = self.data_dir / "world_cup_2026_squads.json"
        with open(profiles_file, 'w') as f:
            # Convert for JSON serialization
            json_profiles = {}
            for team, profile in squad_profiles.items():
                json_profiles[team] = {
                    'team_pes': profile['team_pes'],
                    'status': profile['status'],
                    'squad_size': profile['squad_size'],
                    'positions': profile['positions'],
                }
            json.dump(json_profiles, f, indent=2)
        print(f"  Squad profiles: {profiles_file}")

        return team_file, player_file, profiles_file

    def run(self, kaggle_csv: str = None) -> tuple:
        """
        Run full World Cup training pipeline
        """
        print("\n" + "="*80)
        print("WORLD CUP 2026 SUBSTITUTION RECOMMENDATION SYSTEM")
        print("Training exclusively on 48 World Cup teams")
        print("="*80)

        # Load and process data
        print("\nSTEP 1: DATA LOADING")
        player_pes_df, _ = self.loader.run_full_pipeline(kaggle_csv)

        if player_pes_df.empty:
            print("\nERROR: No player data loaded")
            return None, None, None

        # Train team PES
        print("\nSTEP 2: TEAM PES COMPUTATION")
        team_pes_df = self.compute_world_cup_team_pes(player_pes_df)

        # Create squad profiles
        print("\nSTEP 3: SQUAD PROFILE CREATION")
        squad_profiles = self.create_squad_profiles(player_pes_df, team_pes_df)

        # Print report
        print("\nSTEP 4: TRAINING REPORT")
        self.print_training_report(team_pes_df, squad_profiles)

        # Save artifacts
        print("\nSTEP 5: SAVING ARTIFACTS")
        team_file, player_file, profiles_file = self.save_training_artifacts(
            team_pes_df, squad_profiles, player_pes_df
        )

        print("\n" + "="*80)
        print("WORLD CUP 2026 TRAINING COMPLETE")
        print("="*80)
        print("\nSystem is ready for:")
        print("  - Live match tracking")
        print("  - Real-time substitution recommendations")
        print("  - Squad analysis and rotation planning")
        print("  - Tournament performance prediction")

        return team_pes_df, player_pes_df, squad_profiles


if __name__ == "__main__":
    trainer = WorldCupTrainer()

    # Run training pipeline
    # If you have Kaggle dataset: trainer.run(kaggle_csv="path/to/dataset.csv")
    team_pes, player_pes, squads = trainer.run()

    if team_pes is not None:
        print("\nTop 8 World Cup Favorites:")
        print(team_pes.head(8)[['team', 'current_pes', 'status', 'squad_size']].to_string(index=False))
