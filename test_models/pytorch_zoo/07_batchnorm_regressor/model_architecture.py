import torch
import torch.nn as nn

class BatchNormRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.BatchNorm1d(32), nn.ReLU(), nn.Linear(32, 16), nn.BatchNorm1d(16), nn.ReLU(), nn.Linear(16, 1))
    def forward(self, x): return self.net(x)

