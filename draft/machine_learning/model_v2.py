import torch
import torch.nn as nn
import torch.nn.functional as F

class DraftTransformerModel(nn.Module):
    def __init__(self, num_champions=171, num_teams=200, dropout=0.1):
        super().__init__()
        # +1 for PAD
        self.num_champions = num_champions
        self.champ_embedding = nn.Embedding(num_champions + 1, 64, padding_idx=num_champions)
        self.action_embedding = nn.Embedding(3, 4, padding_idx=0) # 0: PAD, 1: BAN, 2: PICK
        self.side_embedding = nn.Embedding(3, 4, padding_idx=0)   # 0: PAD, 1: BLUE, 2: RED
        self.pos_embedding = nn.Embedding(20, 8)
        self.team_embedding = nn.Embedding(num_teams, 16)
        self.opp_team_embedding = nn.Embedding(num_teams, 16)
        
        # Combined draft slot token dimension: 64 + 4 + 4 + 8 = 80
        # Transformer hidden size: 128
        self.input_projection = nn.Linear(80, 128)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=128, 
            nhead=8, 
            dim_feedforward=512, 
            dropout=dropout,
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=4)
        
        # State pooling (128) + team embedding (16) + opp team embedding (16) = 160
        self.output_head = nn.Sequential(
            nn.Linear(160, 256),
            nn.ReLU(),
            nn.Linear(256, num_champions)
        )

    def forward(self, champ_ids, action_types, sides, positions, team_idx, opp_team_idx=None):
        """
        champ_ids: (batch, 20) - indices 0..170, 171 for PAD
        action_types: (batch, 20) - 0: PAD, 1: BAN, 2: PICK
        sides: (batch, 20) - 0: PAD, 1: BLUE, 2: RED
        positions: (batch, 20) - 0..19
        team_idx: (batch,) - team index
        opp_team_idx: (batch,) - opponent team index
        """
        # Embeddings
        c_emb = self.champ_embedding(champ_ids)   # (batch, 20, 64)
        a_emb = self.action_embedding(action_types) # (batch, 20, 4)
        s_emb = self.side_embedding(sides)         # (batch, 20, 4)
        p_emb = self.pos_embedding(positions)       # (batch, 20, 8)
        
        # Concatenate features for each slot
        x = torch.cat([c_emb, a_emb, s_emb, p_emb], dim=-1) # (batch, 20, 80)
        
        # Project to transformer dimension
        x = self.input_projection(x) # (batch, 20, 128)
        
        # Transformer mask for padding (True where padding exists)
        # Using the PAD index of champion_embedding
        src_key_padding_mask = (champ_ids == self.num_champions)
        
        # All-masked sequences cause RuntimeError in some PyTorch versions
        all_masked = src_key_padding_mask.all(dim=1)
        if all_masked.any():
            src_key_padding_mask[all_masked, 0] = False
        
        # Transformer Encoder
        x = self.transformer_encoder(x, src_key_padding_mask=src_key_padding_mask) # (batch, 20, 128)
        
        # Mean pooling of tokens (ignoring padding)
        # Create a mask that is 1 for real tokens and 0 for padding
        mask = (~src_key_padding_mask).float().unsqueeze(-1) # (batch, 20, 1)
        x_masked = x * mask
        pooled = x_masked.sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9) # (batch, 128)
        
        # Concatenate team embeddings
        t_emb = self.team_embedding(team_idx) # (batch, 16)
        if opp_team_idx is None:
            # Fallback for old calls or unknown opponent
            opp_team_idx = torch.zeros_like(team_idx)
        o_emb = self.opp_team_embedding(opp_team_idx) # (batch, 16)
        
        state_vec = torch.cat([pooled, t_emb, o_emb], dim=-1) # (batch, 160)
        
        # Output head
        logits = self.output_head(state_vec) # (batch, 171)
        return logits
