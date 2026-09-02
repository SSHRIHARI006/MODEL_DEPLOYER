"""Generate 12 deterministic scikit-learn models for the Model Deployer zoo.

Usage: python test_models/sklearn_zoo/generate_all.py
"""
import shutil
import zipfile
from pathlib import Path

import joblib
import numpy as np
import sklearn
import yaml
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier

ZOO_ROOT = Path(__file__).resolve().parent
# Pickled estimators are only guaranteed to load under the sklearn version
# that trained them (private C-extension modules move between releases), so
# the serving env must pin the exact training version.
REQUIREMENTS = f"scikit-learn=={sklearn.__version__}\n"

MODELS = [
    ("01_linear_regression", LinearRegression(), "regression"),
    ("02_ridge", Ridge(alpha=1.0), "regression"),
    ("03_logistic_regression_binary", LogisticRegression(max_iter=500, random_state=42), "classification"),
    ("04_logistic_regression_multiclass", LogisticRegression(max_iter=500, random_state=42), "classification"),
    ("05_svc_linear", SVC(kernel="linear"), "classification"),
    ("06_svr_rbf", SVR(kernel="rbf"), "regression"),
    ("07_decision_tree_classifier", DecisionTreeClassifier(random_state=42), "classification"),
    ("08_random_forest_classifier", RandomForestClassifier(n_estimators=25, random_state=42), "classification"),
    ("09_random_forest_regressor", RandomForestRegressor(n_estimators=25, random_state=42), "regression"),
    ("10_gradient_boosting_classifier", GradientBoostingClassifier(random_state=42), "classification"),
    ("11_knn_classifier", KNeighborsClassifier(n_neighbors=3), "classification"),
    ("12_mlp_classifier", MLPClassifier(hidden_layer_sizes=(16, 8), max_iter=800, random_state=42), "classification"),
]


def _dataset(name, task):
    if task == "regression":
        return make_regression(n_samples=200, n_features=4, noise=0.1, random_state=42)
    n_classes = 3 if "multiclass" in name else 2
    return make_classification(
        n_samples=200,
        n_features=4,
        n_informative=4,
        n_redundant=0,
        n_classes=n_classes,
        n_clusters_per_class=1,
        random_state=42,
    )


def generate():
    for name, estimator, task in MODELS:
        model_dir = ZOO_ROOT / name
        if model_dir.exists():
            shutil.rmtree(model_dir)
        model_dir.mkdir(parents=True)

        X, y = _dataset(name, task)
        estimator.fit(X, y)
        joblib.dump(estimator, model_dir / "model.pkl")

        manifest = {
            "name": name,
            "framework": "sklearn",
            "python_version": "3.12",
            "requirements": "requirements.txt",
            "model_artifact": "model.pkl",
            "task_type": task,
        }
        (model_dir / "model.yaml").write_text(yaml.dump(manifest, sort_keys=False))
        (model_dir / "requirements.txt").write_text(REQUIREMENTS)

        zip_path = model_dir / f"{name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_name in ("model.yaml", "requirements.txt", "model.pkl"):
                archive.write(model_dir / file_name, file_name)

        print(f"  [{task:>14}] {name}")

    print(f"\nGenerated {len(MODELS)} models in {ZOO_ROOT}")


if __name__ == "__main__":
    print("Generating sklearn Model Zoo...\n")
    generate()
