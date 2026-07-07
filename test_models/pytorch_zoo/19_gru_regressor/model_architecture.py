import torch
import torch.nn as nn

class GRURegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru = nn.GRU(input_size=1, hidden_size=16, batch_first=True)
        self.fc = nn.Linear(16, 1)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(-1)
        _, h = self.gru(x)
        return self.fc(h.squeeze(0))

