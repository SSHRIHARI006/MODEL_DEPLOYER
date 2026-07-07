import torch
import torch.nn as nn

class BinaryClassifier(nn.Module):
    def __init__(self): super().__init__(); self.net = nn.Sequential(nn.Linear(4, 16), nn.ReLU(), nn.Linear(16, 1))
    def forward(self, x): return self.net(x)

