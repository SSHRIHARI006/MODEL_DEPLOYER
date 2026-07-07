import torch
import torch.nn as nn

class TanhClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.Tanh(), nn.Linear(32, 16), nn.Tanh(), nn.Linear(16, 3))
    def forward(self, x): return self.net(x)

