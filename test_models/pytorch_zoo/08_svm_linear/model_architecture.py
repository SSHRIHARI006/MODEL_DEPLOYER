import torch
import torch.nn as nn

class SVMLinear(nn.Module):
    def __init__(self): super().__init__(); self.fc = nn.Linear(4, 3)
    def forward(self, x): return self.fc(x)

