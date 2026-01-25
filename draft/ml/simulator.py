import torch
from .encoder import encode_state

class DraftSimulator:
    def __init__(self, model, champion_ids, champion_to_idx):
        self.model = model
        self.champion_ids = champion_ids
        self.champion_to_idx = champion_to_idx
        self.reset()

    def reset(self):
        self.state = {
            "picked_blue": set(),
            "picked_red": set(),
            "banned_blue": set(),
            "banned_red": set(),
        }
        self.history = []

    def legal_actions(self):
        used = (
            self.state["picked_blue"]
            | self.state["picked_red"]
            | self.state["banned_blue"]
            | self.state["banned_red"]
        )
        return [c for c in self.champion_ids if c not in used]

    def suggest(self, side, action_type, step, top_k=5):
        s = {
            **self.state,
            "side": side,
            "action_type": action_type,
            "step": step,
        }

        x = torch.tensor(
            encode_state(s, self.champion_to_idx, self.champion_ids)
        ).float().unsqueeze(0)

        logits = self.model(x).squeeze(0)

        legal = self.legal_actions()
        mask = torch.full_like(logits, float("-inf"))

        for c in legal:
            idx = self.champion_to_idx[c]
            mask[idx] = logits[idx]

        probs = torch.softmax(mask, dim=0)

        top = torch.topk(probs, top_k)
        entropy = -(probs * torch.log(probs + 1e-9)).sum().item()

        return {
            "suggestions": [
                (self.champion_ids[i], probs[i].item())
                for i in top.indices
            ],
            "entropy": entropy,
        }

    def apply(self, champion, side, action_type):
        key = f"{action_type.lower()}ed_{side.lower()}"
        self.state[key].add(champion)
        self.history.append((side, action_type, champion))
