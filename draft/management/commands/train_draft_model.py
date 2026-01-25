import os
import torch
import torch.nn as nn
import torch.optim as optim
from django.core.management.base import BaseCommand
from draft.machine_learning.model_v2 import DraftTransformerModel
from draft.machine_learning.dataset_v2 import prepare_data, DraftDatasetV2, get_champion_mapping, get_team_mapping
from torch.utils.data import DataLoader
import json

class Command(BaseCommand):
    help = "Train the new Transformer-based draft model (V3)"

    def add_arguments(self, parser):
        parser.add_argument('--epochs', type=int, default=10, help='Number of epochs to train')

    def handle(self, *args, **options):
        self.stdout.write("Preparing data...")
        games_data, champ_to_idx, team_to_idx, num_champions = prepare_data()
        
        # Get reverse mappings for saving
        from draft.machine_learning.dataset_v2 import get_champion_mapping
        _, idx_to_champ, idx_to_name = get_champion_mapping()
        
        num_teams = len(team_to_idx) + 1 # +1 for unknown
        
        dataset = DraftDatasetV2(games_data, champ_to_idx, team_to_idx, num_champions)
        self.stdout.write(f"Found {len(dataset)} training samples.")
        
        dataloader = DataLoader(dataset, batch_size=64, shuffle=True)
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = DraftTransformerModel(num_champions=num_champions, num_teams=num_teams).to(device)
        
        artifacts_dir = "draft/ml_artifacts"
        save_path = os.path.join(artifacts_dir, "draft_model_v3.pth")
        
        if os.path.exists(save_path):
            self.stdout.write("Loading existing model weights for incremental training...")
            try:
                model.load_state_dict(torch.load(save_path, map_location=device))
            except Exception as e:
                self.stdout.write(f"Could not load weights: {e}. Starting from scratch.")

        optimizer = optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
        
        model.train()
        num_epochs = options['epochs']
        for epoch in range(num_epochs):
            total_loss = 0
            for i, batch in enumerate(dataloader):
                champ_ids, action_types, sides, positions, team_idx, opp_team_idx, target_champ = [t.to(device) for t in batch]
                
                optimizer.zero_grad()
                logits = model(champ_ids, action_types, sides, positions, team_idx, opp_team_idx)
                loss = criterion(logits, target_champ)
                loss.backward()
                optimizer.step()
                
                total_loss += loss.item()
                
                if (i + 1) % 100 == 0:
                    self.stdout.write(f"Epoch {epoch+1}, Batch {i+1}/{len(dataloader)}, Loss: {loss.item():.4f}")
            
            self.stdout.write(f"Epoch {epoch+1}/{num_epochs} COMPLETED, Avg Loss: {total_loss/len(dataloader):.4f}")
            
        # Save model and mappings
        artifacts_dir = "draft/ml_artifacts"
        os.makedirs(artifacts_dir, exist_ok=True)
        
        save_path = os.path.join(artifacts_dir, "draft_model_v3.pth")
        torch.save(model.state_dict(), save_path)
        
        mappings = {
            "champ_to_idx": champ_to_idx,
            "idx_to_champ": idx_to_champ,
            "idx_to_name": idx_to_name,
            "team_to_idx": team_to_idx,
            "num_champions": num_champions,
            "num_teams": num_teams
        }
        with open(os.path.join(artifacts_dir, "draft_mappings_v3.json"), 'r' if os.path.exists(os.path.join(artifacts_dir, "draft_mappings_v3.json")) else 'w') as f:
             # Just overwrite it
             pass
        with open(os.path.join(artifacts_dir, "draft_mappings_v3.json"), 'w') as f:
            json.dump(mappings, f)
            
        self.stdout.write(f"Model saved to {save_path}")
        self.stdout.write(f"Mappings saved to {os.path.join(artifacts_dir, 'draft_mappings_v3.json')}")
