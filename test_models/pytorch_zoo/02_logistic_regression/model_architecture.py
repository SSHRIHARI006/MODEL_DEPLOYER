import torch
import torch.nn as nn

class LogisticRegression(nn.Module):
    def __init__(self): super().__init__(); self.fc = nn.Linear(4, 1)
    def forward(self, x): return torch.sigmoid(self.fc(x))

