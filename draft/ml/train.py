import torch
import torch.nn as nn
from torch.utils.data import DataLoader

def train(model, dataset, epochs=20, lr=1e-3):
    loader = DataLoader(dataset, batch_size=64, shuffle=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss(reduction="none")

    for epoch in range(epochs):
        total_loss = 0.0

        for X, y, w in loader:
            logits = model(X)
            losses = loss_fn(logits, y)
            loss = (losses * w).mean()

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        print(f"Epoch {epoch}: {total_loss:.4f}")
