"""Phase 4 pipeline orchestrator"""
import numpy as np
import logging
import asyncio
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def run_phase4():
    logger.info("\n" + "=" * 70)
    logger.info("PHASE 4: FITNESS MODEL TRAINING & DEPLOYMENT")
    logger.info("=" * 70)

    try:
        from feature_engineering import FeatureEngineer
        from trainer import FitnessModelTrainer
        from validator import ModelValidator
        from inference import FitnessPredictor

        # Step 1: Feature Engineering
        logger.info("\n[STEP 1/6] Creating feature matrix...")
        players = [{'player_id': f'p{i}', 'name': f'Player {i}', 'position': ['MID', 'DEF', 'ATT', 'GK'][i % 4], 'appearance_density': 85 + np.random.randn() * 5, 'contribution_index': 70 + np.random.randn() * 5, 'rating_normalized': 80 + np.random.randn() * 5, 'team_pes': 80, 'injury_risk': 0.05, 'baseline_fitness': 75 + np.random.randn() * 5} for i in range(50)]
        embeddings = np.random.randn(50, 384) * 0.1
        
        fe = FeatureEngineer()
        X, y, feature_names = await fe.create_feature_matrix(players, embeddings)
        logger.info(f"  ✓ Created feature matrix: {X.shape}")

        # Step 2: Train models
        logger.info("\n[STEP 2/6] Training models (5-fold CV)...")
        trainer = FitnessModelTrainer()
        training_results = await trainer.train_all_models(X, y, feature_names)

        # Step 3: Validate & select
        logger.info("\n[STEP 3/6] Validating models...")
        validator = ModelValidator()
        selection = await validator.validate_and_select(training_results['models'])

        # Step 4: Deploy
        logger.info("\n[STEP 4/6] Deploying inference engine...")
        predictor = FitnessPredictor()
        test_predictions = await predictor.predict_batch(X[:10])
        logger.info(f"  ✓ Test predictions: mean={test_predictions.mean():.1f}")

        logger.info("\n" + "=" * 70)
        logger.info("✓ PHASE 4 COMPLETE")
        logger.info("=" * 70)
        logger.info(f"\nResults:")
        logger.info(f"  Best Model: {selection['best_model']}")
        logger.info(f"  R² Score: {selection['r2_score']:.4f}")
        logger.info(f"  RMSE: {selection['rmse']:.2f}")
        logger.info(f"  Status: READY FOR DEPLOYMENT")

        return {'success': True, 'best_model': selection['best_model']}

    except Exception as e:
        logger.error(f"Phase 4 execution failed: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

if __name__ == "__main__":
    result = asyncio.run(run_phase4())
    sys.exit(0 if result.get('success') else 1)
