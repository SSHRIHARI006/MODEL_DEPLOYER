import torch
import torch.nn as nn

class LeakyReLUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(4, 32), nn.LeakyReLU(0.1), nn.Linear(32, 16), nn.LeakyReLU(0.1), nn.Linear(16, 1))
    def forward(self, x): return self.net(x)

