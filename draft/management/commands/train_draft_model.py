import numpy as np
from django.core.management.base import BaseCommand
from draft.models import DraftAction, Champion
from draft.ml.encoder import encode_state
from draft.ml.model import DraftPolicyNet
import torch
import torch.nn as nn
from collections import defaultdict
from draft.ml.phase import get_draft_phase
from tqdm import tqdm

class Command(BaseCommand):
    help = "Train draft model from historical drafts"

    def handle(self, *args, **options):
        device = "cuda" if torch.cuda.is_available() else "cpu"


        # --- Step 1: Build mappings ---
        champions = Champion.objects.all()
        champion_id_to_index = {c.id: idx for idx, c in enumerate(champions)}
        NUM_CHAMPIONS = len(champions)

        drafter_ids = DraftAction.objects.values_list("drafter_id", flat=True).distinct()
        team_ids = list(sorted(set(drafter_ids)))
        team_id_to_index = {tid: idx for idx, tid in enumerate(team_ids)}
        NUM_TEAMS = len(team_ids)

        # --- Step 2: Load draft actions in order ---
        actions = DraftAction.objects.select_related("champion").order_by("game_id", "sequence_number")
        drafts_by_game = {}
        for a in actions:
            drafts_by_game.setdefault(a.game_id, []).append(a)

        X_list, Y_list = [], []
        opp_team_indices = []

        # --- Step 3: Encode each draft step ---
        for game_id, steps in tqdm(drafts_by_game.items(), desc="Encoding drafts"):
            picked_blue = []
            picked_red = []
            banned = []

            # Identify blue and red team indices for this game
            blue_team_idx = None
            red_team_idx = None
            for step in steps:
                if step.team_side.upper() == "BLUE":
                    blue_team_idx = team_id_to_index.get(step.drafter_id)
                elif step.team_side.upper() == "RED":
                    red_team_idx = team_id_to_index.get(step.drafter_id)
                if blue_team_idx is not None and red_team_idx is not None:
                    break
            
            if blue_team_idx is None or red_team_idx is None:
                continue

            for step in steps:
                # Skip if champion not in mapping
                if step.champion_id not in champion_id_to_index:
                    continue

                champ_idx = champion_id_to_index[step.champion_id]
                team_idx = team_id_to_index[step.drafter_id]
                opp_idx = red_team_idx if step.team_side.upper() == "BLUE" else blue_team_idx
                
                phase = get_draft_phase(step.sequence_number)

                side_upper = step.team_side.upper()
                if side_upper == "BLUE":
                    own_picks = picked_blue
                    enemy_picks = picked_red
                else:
                    own_picks = picked_red
                    enemy_picks = picked_blue

                # Encode current state
                state = encode_state(
                    own_picks=own_picks,
                    enemy_picks=enemy_picks,
                    banned_champions=banned,
                    team_idx=team_idx,
                    side=step.team_side,
                    phase=phase,
                    champion_id_to_index=champion_id_to_index
                )

                # Append to dataset
                X_list.append(state)
                Y_list.append(champ_idx)
                opp_team_indices.append(opp_idx)

                # Update picked/banned lists
                if step.action_type.upper() == "PICK":
                    if side_upper == "BLUE":
                        picked_blue.append(champ_idx)
                    else:
                        picked_red.append(champ_idx)
                elif step.action_type.upper() == "BAN":
                    banned.append(champ_idx)

        print(f"Encoded {len(X_list)} samples")

        # --- Step 4: Convert to PyTorch tensors ---
        feature_vectors = []
        team_indices = []
        for s in X_list:
            vec = np.concatenate([
                s["own_picks"],
                s["enemy_picks"],
                s["bans"],
                s["side"],
                s["phase"],
                s["role_pressure"],
            ])
            feature_vectors.append(vec)
            team_indices.append(s["team_idx"])

        X_tensor = torch.tensor(np.stack(feature_vectors), dtype=torch.float32).to(device)
        T_tensor = torch.tensor(team_indices, dtype=torch.long).to(device)
        O_tensor = torch.tensor(opp_team_indices, dtype=torch.long).to(device)
        Y_tensor = torch.tensor(Y_list, dtype=torch.long).to(device)

        input_dim = X_tensor.shape[1]  # feature vector length
        num_champions = len(champion_id_to_index)

        model = DraftPolicyNet(input_dim=input_dim, num_champions=num_champions, num_teams=NUM_TEAMS).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        loss_fn = nn.CrossEntropyLoss()

        self.stdout.write("Training model...")

        for epoch in range(200):
            optimizer.zero_grad()
            logits = model(X_tensor, T_tensor, O_tensor)
            loss = loss_fn(logits, Y_tensor)
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 50 == 0 or epoch == 0:
                self.stdout.write(f"Epoch {epoch+1}: loss={loss.item():.4f}")

        torch.save({
                "model_state": model.state_dict(),
                "champion_id_to_index": champion_id_to_index,
                "team_id_to_index": team_id_to_index,
                "input_dim": input_dim,
                "num_champions": num_champions,
                "num_teams": NUM_TEAMS
            },
        "draft/ml_artifacts/draft_model.pt"  # example subfolder
        )

        self.stdout.write(self.style.SUCCESS("Model trained & saved"))
