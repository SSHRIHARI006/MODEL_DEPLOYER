import torch
import torch.nn as nn

class RNNClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.rnn = nn.RNN(input_size=1, hidden_size=16, batch_first=True)
        self.fc = nn.Linear(16, 3)
    def forward(self, x):
        if x.dim() == 2: x = x.unsqueeze(-1)
        _, h = self.rnn(x)
        return self.fc(h.squeeze(0))

