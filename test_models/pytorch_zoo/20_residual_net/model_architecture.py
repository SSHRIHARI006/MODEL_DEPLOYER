import torch
import torch.nn as nn

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

