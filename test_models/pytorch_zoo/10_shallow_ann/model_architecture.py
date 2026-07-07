import torch
import torch.nn as nn

class ShallowANN(nn.Module):
    def __init__(self): super().__init__(); self.net = nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 3))
    def forward(self, x): return self.net(x)

