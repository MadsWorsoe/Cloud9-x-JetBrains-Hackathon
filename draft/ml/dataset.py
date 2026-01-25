import torch
from torch.utils.data import Dataset

class DraftDataset(Dataset):
    def __init__(self, samples):
        self.X = torch.tensor(
            [s["x"] for s in samples],
            dtype=torch.float32
        )
        self.y = torch.tensor(
            [s["label"] for s in samples],
            dtype=torch.long
        )
        self.w = torch.tensor(
            [s["weight"] for s in samples],
            dtype=torch.float32
        )

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx], self.w[idx]
