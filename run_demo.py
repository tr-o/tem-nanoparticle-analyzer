"""Regenerate synthetic training data, fit RF and export all test results."""
from pathlib import Path
from tem_particle_ml import generate_demo, fit_model, evaluation, save_inference

root = Path(__file__).resolve().parent
data = root / 'demo_data'
generate_demo(data, train=16, test=4)
model = root / 'trained_rf.joblib'
fit_model(data/'train/images', data/'train/masks', model)
print('TEST', evaluation(model, data/'test/images', data/'test/masks', root/'test_metrics.json'))
for i in range(4):
    save_inference(data/'test/images'/f'test_{i:02d}.png',
                   model, root/f'results/test_{i:02d}', nm_per_px=.4)
print('FINISHED: results/test_00/overview.png and particles.csv')
