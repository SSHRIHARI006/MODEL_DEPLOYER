import torch
import torch.nn as nn

class LinearRegression(nn.Module):
    def __init__(self): super().__init__(); self.fc = nn.Linear(4, 1)
    def forward(self, x): return self.fc(x)

