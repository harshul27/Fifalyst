"""Feature engineering for model training"""
import numpy as np
import logging

logger = logging.getLogger(__name__)

class FeatureEngineer:
    def __init__(self):
        self.feature_names = None

    async def create_feature_matrix(self, real_players, embeddings):
        logger.info(f"Creating feature matrix for {len(real_players)} players...")
        X = embeddings.copy()
        engineered = []
        for player in real_players:
            features = [
                player.get('appearance_density', 0),
                player.get('contribution_index', 0),
                player.get('rating_normalized', 0),
                player.get('team_pes', 75),
                player.get('injury_risk', 0.05),
            ] + self._position_encode(player.get('position', 'MID'))
            engineered.append(features)
        
        engineered_arr = np.array(engineered)
        X = np.hstack([X, engineered_arr])
        y = np.array([p.get('baseline_fitness', 75) for p in real_players])
        
        embedding_names = [f'emb_{i}' for i in range(384)]
        engineered_names = ['appearance_density', 'contribution_index', 'rating_norm', 'team_pes', 'injury_risk', 'pos_gk', 'pos_def', 'pos_mid', 'pos_att']
        self.feature_names = embedding_names + engineered_names
        
        logger.info(f"✓ Created feature matrix: {X.shape}")
        return X, y, self.feature_names

    @staticmethod
    def _position_encode(position):
        pos_map = {'GK': [1, 0, 0, 0], 'DEF': [0, 1, 0, 0], 'MID': [0, 0, 1, 0], 'ATT': [0, 0, 0, 1]}
        return pos_map.get(position, [0, 0, 0, 0])

async def main():
    players = [{'player_id': f'p{i}', 'name': f'Player {i}', 'position': 'MID', 'appearance_density': 85, 'contribution_index': 70, 'rating_normalized': 80, 'team_pes': 80, 'injury_risk': 0.05, 'baseline_fitness': 75} for i in range(10)]
    embeddings = np.random.randn(10, 384) * 0.1
    fe = FeatureEngineer()
    X, y, names = await fe.create_feature_matrix(players, embeddings)
    print(f"Feature matrix: {X.shape}")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
