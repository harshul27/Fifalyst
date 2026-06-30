"""Model validator"""
import json
import logging

logger = logging.getLogger(__name__)

class ModelValidator:
    async def validate_and_select(self, results):
        logger.info("MODEL VALIDATION & SELECTION")
        
        best_model = max(results.items(), key=lambda x: x[1]['r2_score'])[0]
        best_metrics = results[best_model]
        
        selection = {
            'best_model': best_model,
            'metrics': best_metrics,
            'r2_score': best_metrics['r2_score'],
            'rmse': best_metrics.get('rmse_mean', best_metrics.get('rmse'))
        }
        
        logger.info(f"✓ Selected {best_model}: R²={selection['r2_score']:.4f}")
        
        with open('models/model_selection.json', 'w') as f:
            json.dump(selection, f, indent=2)
        
        return selection

async def main():
    validator = ModelValidator()
    results = {'xgboost': {'r2_score': 0.86, 'rmse_mean': 7.0}, 'rule_based': {'r2_score': 0.78, 'rmse': 9.0}}
    sel = await validator.validate_and_select(results)
    print(f"Best: {sel['best_model']}")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
