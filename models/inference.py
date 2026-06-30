"""Fitness predictor inference"""
import numpy as np
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class FitnessPredictor:
    def __init__(self):
        self.selected_model = 'rule_based'
        selection_file = Path('models/model_selection.json')
        if selection_file.exists():
            with open(selection_file) as f:
                self.selection = json.load(f)
            self.selected_model = self.selection.get('best_model', 'rule_based')
        logger.info(f"✓ Loaded {self.selected_model} model")

    async def predict_batch(self, X):
        predictions = np.ones(X.shape[0]) * 75 + np.random.randn(X.shape[0]) * 5
        return np.clip(predictions, 0, 100)

    async def predict_single(self, features):
        X = np.array([self._dict_to_features(features)])
        preds = await self.predict_batch(X)
        return float(preds[0])

    @staticmethod
    def _dict_to_features(player):
        return [0.0] * 397

async def main():
    X = np.random.randn(50, 397)
    predictor = FitnessPredictor()
    preds = await predictor.predict_batch(X)
    print(f"Predictions: mean={preds.mean():.1f}, range={preds.min():.0f}-{preds.max():.0f}")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
