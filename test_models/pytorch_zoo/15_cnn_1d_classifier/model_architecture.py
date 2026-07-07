import torch
import torch.nn as nn

class CNN1DClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(1, 8, kernel_size=2, padding=1), nn.ReLU(), nn.AdaptiveAvgPool1d(1))
        self.fc = nn.Linear(8, 3)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(1)
        return self.fc(self.conv(x).squeeze(-1))

