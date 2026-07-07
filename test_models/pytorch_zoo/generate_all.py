"""Generate 20 diverse PyTorch models for the Model Deployer zoo.

Usage: python test_models/pytorch_zoo/generate_all.py
"""
import os, sys, json, shutil
from pathlib import Path

import torch
import torch.nn as nn
import numpy as np

ZOO_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Model Architecture Definitions
# ---------------------------------------------------------------------------

class LinearRegression(nn.Module):
    def __init__(self): super().__init__(); self.fc = nn.Linear(4, 1)
    def forward(self, x): return self.fc(x)

class LogisticRegression(nn.Module):
    def __init__(self): super().__init__(); self.fc = nn.Linear(4, 1)
    def forward(self, x): return torch.sigmoid(self.fc(x))

class BinaryClassifier(nn.Module):
    def __init__(self): super().__init__(); self.net = nn.Sequential(nn.Linear(4, 16), nn.ReLU(), nn.Linear(16, 1))
    def forward(self, x): return self.net(x)

class MulticlassClassifier(nn.Module):
    def __init__(self): super().__init__(); self.net = nn.Sequential(nn.Linear(4, 32), nn.ReLU(), nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 3))
    def forward(self, x): return self.net(x)

class DeepMLPRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 8), nn.ReLU(), nn.Linear(8, 1))
    def forward(self, x): return self.net(x)

class DropoutClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.ReLU(), nn.Dropout(0.3), nn.Linear(32, 16), nn.ReLU(), nn.Dropout(0.3), nn.Linear(16, 3))
    def forward(self, x): return self.net(x)

class BatchNormRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.BatchNorm1d(32), nn.ReLU(), nn.Linear(32, 16), nn.BatchNorm1d(16), nn.ReLU(), nn.Linear(16, 1))
    def forward(self, x): return self.net(x)

class SVMLinear(nn.Module):
    def __init__(self): super().__init__(); self.fc = nn.Linear(4, 3)
    def forward(self, x): return self.fc(x)

class DecisionBoundary(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 3))
    def forward(self, x): return self.net(x)

class ShallowANN(nn.Module):
    def __init__(self): super().__init__(); self.net = nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 3))
    def forward(self, x): return self.net(x)

class DeepANN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 8), nn.ReLU(), nn.Linear(8, 3))
    def forward(self, x): return self.net(x)

class ReLUTower(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1))
    def forward(self, x): return self.net(x)

class LeakyReLUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.LeakyReLU(0.1), nn.Linear(32, 16), nn.LeakyReLU(0.1), nn.Linear(16, 1))
    def forward(self, x): return self.net(x)

class TanhClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.Tanh(), nn.Linear(32, 16), nn.Tanh(), nn.Linear(16, 3))
    def forward(self, x): return self.net(x)

class CNN1DClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(1, 8, kernel_size=2, padding=1), nn.ReLU(), nn.AdaptiveAvgPool1d(1))
        self.fc = nn.Linear(8, 3)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(1)
        return self.fc(self.conv(x).squeeze(-1))

class CNN1DRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(1, 8, kernel_size=2, padding=1), nn.ReLU(), nn.AdaptiveAvgPool1d(1))
        self.fc = nn.Linear(8, 1)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(1)
        return self.fc(self.conv(x).squeeze(-1))

class RNNClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.rnn = nn.RNN(input_size=1, hidden_size=16, batch_first=True)
        self.fc = nn.Linear(16, 3)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(-1)
        _, h = self.rnn(x)
        return self.fc(h.squeeze(0))

class LSTMClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(input_size=1, hidden_size=16, batch_first=True)
        self.fc = nn.Linear(16, 3)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(-1)
        _, (h, _) = self.lstm(x)
        return self.fc(h.squeeze(0))

class GRURegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru = nn.GRU(input_size=1, hidden_size=16, batch_first=True)
        self.fc = nn.Linear(16, 1)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(-1)
        _, h = self.gru(x)
        return self.fc(h.squeeze(0))

class ResidualBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.block = nn.Sequential(nn.Linear(dim, dim), nn.ReLU(), nn.Linear(dim, dim))
        self.relu = nn.ReLU()
    def forward(self, x): return self.relu(self.block(x) + x)

class ResidualNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = nn.Linear(4, 32)
        self.res1 = ResidualBlock(32)
        self.res2 = ResidualBlock(32)
        self.head = nn.Linear(32, 3)
    def forward(self, x): return self.head(self.res2(self.res1(self.proj(x))))

# ---------------------------------------------------------------------------
# Model Zoo Specification
# ---------------------------------------------------------------------------

MODELS = [
    {"name": "01_linear_regression",      "cls": LinearRegression,      "task": "regression",             "input": "tabular"},
    {"name": "02_logistic_regression",     "cls": LogisticRegression,    "task": "binary_classification",  "input": "tabular"},
    {"name": "03_binary_classifier",       "cls": BinaryClassifier,      "task": "binary_classification",  "input": "tabular"},
    {"name": "04_multiclass_classifier",   "cls": MulticlassClassifier,  "task": "classification",         "input": "tabular"},
    {"name": "05_deep_mlp_regressor",      "cls": DeepMLPRegressor,      "task": "regression",             "input": "tabular"},
    {"name": "06_dropout_classifier",      "cls": DropoutClassifier,     "task": "classification",         "input": "tabular"},
    {"name": "07_batchnorm_regressor",     "cls": BatchNormRegressor,    "task": "regression",             "input": "tabular"},
    {"name": "08_svm_linear",              "cls": SVMLinear,             "task": "classification",         "input": "tabular"},
    {"name": "09_decision_boundary",       "cls": DecisionBoundary,      "task": "classification",         "input": "tabular"},
    {"name": "10_shallow_ann",             "cls": ShallowANN,            "task": "classification",         "input": "tabular"},
    {"name": "11_deep_ann",                "cls": DeepANN,               "task": "classification",         "input": "tabular"},
    {"name": "12_relu_tower",              "cls": ReLUTower,             "task": "regression",             "input": "tabular"},
    {"name": "13_leaky_relu_net",          "cls": LeakyReLUNet,          "task": "regression",             "input": "tabular"},
    {"name": "14_tanh_classifier",         "cls": TanhClassifier,        "task": "classification",         "input": "tabular"},
    {"name": "15_cnn_1d_classifier",       "cls": CNN1DClassifier,       "task": "classification",         "input": "image_1d"},
    {"name": "16_cnn_1d_regressor",        "cls": CNN1DRegressor,        "task": "regression",             "input": "image_1d"},
    {"name": "17_rnn_classifier",          "cls": RNNClassifier,         "task": "classification",         "input": "sequence"},
    {"name": "18_lstm_classifier",         "cls": LSTMClassifier,        "task": "classification",         "input": "sequence"},
    {"name": "19_gru_regressor",           "cls": GRURegressor,          "task": "regression",             "input": "sequence"},
    {"name": "20_residual_net",            "cls": ResidualNet,           "task": "classification",         "input": "tabular"},
]

REQUIREMENTS = """torch>=2.0.0
numpy>=1.24.0
pyyaml>=6.0
"""

def _train_simple(model, task, n_samples=200, n_features=4, epochs=50):
    """Quick training pass with synthetic data so weights are non-random."""
    X = torch.randn(n_samples, n_features)

    if task == "regression":
        y = X.sum(dim=1, keepdim=True) + torch.randn(n_samples, 1) * 0.1
        loss_fn = nn.MSELoss()
    elif task == "binary_classification":
        y = (X.sum(dim=1, keepdim=True) > 0).float()
        loss_fn = nn.BCEWithLogitsLoss()
    else:
        y = (X[:, 0] * 3).long().clamp(0, 2)
        loss_fn = nn.CrossEntropyLoss()

    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        out = model(X)
        if task in ("regression", "binary_classification"):
            loss = loss_fn(out, y)
        else:
            loss = loss_fn(out, y)
        loss.backward()
        opt.step()
    model.eval()


def generate():
    for spec in MODELS:
        name = spec["name"]
        cls = spec["cls"]
        task = spec["task"]
        input_type = spec["input"]
        cls_name = cls.__name__

        model_dir = ZOO_ROOT / name
        if model_dir.exists():
            shutil.rmtree(model_dir)
        model_dir.mkdir(parents=True)

        # Instantiate and train
        model = cls()
        _train_simple(model, task)

        # Save state_dict
        weights_path = model_dir / "model.pt"
        torch.save(model.state_dict(), weights_path)

        # Write architecture file
        import inspect
        arch_path = model_dir / "model_architecture.py"

        # We need to write the class definition. For classes with dependencies
        # (ResidualNet needs ResidualBlock), include them.
        src_lines = ["import torch", "import torch.nn as nn", ""]

        if cls_name == "ResidualNet":
            src_lines.append(inspect.getsource(ResidualBlock))
            src_lines.append("")

        src_lines.append(inspect.getsource(cls))

        arch_path.write_text("\n".join(src_lines) + "\n")

        # Write model.yaml
        manifest = {
            "name": name,
            "framework": "pytorch",
            "python_version": "3.12",
            "requirements": "requirements.txt",
            "model_artifact": "model.pt",
            "task_type": task,
            "device": "cpu",
            "load_method": "state_dict",
            "model_class_file": "model_architecture.py",
            "model_class_name": cls_name,
            "input_type": input_type,
        }
        import yaml
        (model_dir / "model.yaml").write_text(yaml.dump(manifest, sort_keys=False))

        # Write requirements.txt
        (model_dir / "requirements.txt").write_text(REQUIREMENTS)

        # Create deployable zip
        import zipfile
        zip_path = model_dir / f"{name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in ["model.yaml", "requirements.txt", "model.pt", "model_architecture.py"]:
                zf.write(model_dir / f, f)

        print(f"  [{spec['task']:>24}] {name}")

    print(f"\nGenerated {len(MODELS)} models in {ZOO_ROOT}")


if __name__ == "__main__":
    print("Generating PyTorch Model Zoo...\n")
    generate()
