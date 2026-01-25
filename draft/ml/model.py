import torch
import torch.nn as nn

class DraftPolicyNet(nn.Module):
    def __init__(self, input_dim, num_champions, num_teams, team_embedding_dim=16):
        super().__init__()
        self.team_embedding = nn.Embedding(num_teams, team_embedding_dim)
        self.opp_team_embedding = nn.Embedding(num_teams, team_embedding_dim)

        self.net = nn.Sequential(
            nn.Linear(input_dim + (team_embedding_dim * 2), 512),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Linear(256, num_champions),
        )

    def forward(self, x, team_idx, opp_team_idx):
        team_embed = self.team_embedding(team_idx)
        opp_embed = self.opp_team_embedding(opp_team_idx)
        x = torch.cat([x, team_embed, opp_embed], dim=1)
        return self.net(x)
