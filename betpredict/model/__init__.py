"""Robot v2 — motorul de probabilități (feature-uri walk-forward, Dixon-Coles, ELO, LightGBM,
stacking cu piața, calibrare pe piață) + harness de backtest walk-forward.

Jurnalul de predicții rămâne pe ``MODEL_VERSION`` (robot-v1) ca statisticile să nu se rupă;
versiunea motorului este ``ENGINE_VERSION`` și se vede în ``model_registry`` / ``meta``."""

ENGINE_VERSION = "robot-v2"
