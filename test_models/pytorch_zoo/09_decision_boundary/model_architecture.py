import torch
import torch.nn as nn

class DecisionBoundary(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 3))
    def forward(self, x): return self.net(x)

