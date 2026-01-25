from django.core.management.base import BaseCommand
import numpy as np
from pathlib import Path
from matches.models import Game
from draft.models import DraftAction
from draft.machine_learning.encoder import DraftModelEncoder
import joblib
from sklearn.ensemble import RandomForestClassifier  # Changed from GradientBoostingClassifier
import random


class Command(BaseCommand):
    help = "Train an Imitation Learning Model (Predict Next Move)"

    def handle(self, *args, **options):
        # 1. Initialize and Fit Encoder
        self.stdout.write("Initializing Encoder from DB...")
        encoder = DraftModelEncoder().fit()
        num_champs = encoder.num_champions
        num_teams = encoder.num_teams

        # 2. Fetch Games
        games = Game.objects.filter(winning_team__isnull=False).select_related('team_1', 'team_2')
        self.stdout.write(f"Processing {games.count()} games for Action Prediction...")

        X_data = []
        y_data = []  # Target is Champion ID (Integer)

        # 3. Build Dataset (Turn-by-Turn)
        self.stdout.write("Building turn-based dataset...")

        # Limit to recent games or sample if too slow (665 games * 20 turns = 13k rows, easy for GB)
        for game in games.iterator():
            # Get Team IDs
            # Drafter ID is in DraftAction, but let's map game teams
            if game.team_1_side == 'blue':
                blue_team_db_id = game.team_1_id
                red_team_db_id = game.team_2_id
            else:
                blue_team_db_id = game.team_2_id
                red_team_db_id = game.team_1_id

            blue_t_idx = encoder.get_team_id(blue_team_db_id)
            red_t_idx = encoder.get_team_id(red_team_db_id)

            actions = list(DraftAction.objects.filter(game=game).order_by('sequence_number'))

            # State Vectors (Cumulative)
            # We track "Visible Board"
            # We treat Bans and Picks slightly differently or just pools?
            # Let's track: Blue Picks, Red Picks, Blue Bans, Red Bans

            current_b_picks = np.zeros(num_champs)
            current_r_picks = np.zeros(num_champs)
            current_b_bans = np.zeros(num_champs)
            current_r_bans = np.zeros(num_champs)

            for i, action in enumerate(actions):
                # The TARGET is this action's champion
                target_champ_idx = encoder.get_champ_ids([action.champion_id])[0]

                # Input Features for this prediction:
                # 1. Who is acting? (One-Hot or Int? Tree models handle Int okay, One-Hot better)
                # 2. Phase / Turn Number
                # 3. Current Board State

                # Determine acting team
                # DraftAction has `team_side` and `drafter_id`.
                # Ideally we use `drafter_id` to get specific Team ID.
                acting_team_id = encoder.get_team_id(action.drafter_id)
                # If drafter_id is missing, infer from side
                if acting_team_id == 0:
                    acting_team_id = blue_t_idx if action.team_side == 'blue' else red_t_idx

                # --- BUILD FEATURE VECTOR X ---
                # Acting Team (One-Hot)
                acting_team_vec = np.zeros(num_teams)
                if acting_team_id < num_teams: acting_team_vec[acting_team_id] = 1

                # Opponent Team (One-Hot) - Important context!
                opp_team_vec = np.zeros(num_teams)
                opp_id = red_t_idx if action.team_side == 'blue' else blue_t_idx
                if opp_id < num_teams: opp_team_vec[opp_id] = 1

                # Turn Number (Normalized)
                turn_val = i / 20.0

                # Is Pick or Ban? (One-Hot: [is_pick, is_ban])
                type_vec = [1, 0] if action.action_type == 'pick' else [0, 1]

                # Board State (4 vectors)
                # Concatenate all
                full_row = np.concatenate([
                    acting_team_vec,
                    opp_team_vec,
                    [turn_val],
                    type_vec,
                    current_b_picks,
                    current_r_picks,
                    current_b_bans,
                    current_r_bans
                ])

                X_data.append(full_row)
                y_data.append(target_champ_idx)

                # UPDATE STATE for next loop
                if target_champ_idx < num_champs:
                    if action.team_side == 'blue':
                        if action.action_type == 'pick':
                            current_b_picks[target_champ_idx] = 1
                        else:
                            current_b_bans[target_champ_idx] = 1
                    else:
                        if action.action_type == 'pick':
                            current_r_picks[target_champ_idx] = 1
                        else:
                            current_r_bans[target_champ_idx] = 1

        # 4. Train
        X_data = np.array(X_data)
        y_data = np.array(y_data)

        self.stdout.write(f"Training Imitation Model on {len(X_data)} actions...")
        
        # Use RandomForest for fast multi-class prediction
        clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=None,      # Let trees grow deep to learn specific team habits
            n_jobs=-1,           # Use all CPU cores
            random_state=42,
            verbose=1
        )
        clf.fit(X_data, y_data)
        
        acc = clf.score(X_data, y_data)
        self.stdout.write(f"Training Accuracy (Top-1): {acc:.4f}")

        # 5. Save Artifacts
        model_dir = Path("draft/ml_artifacts")
        model_dir.mkdir(exist_ok=True, parents=True)

        model_path = model_dir / "draft_action_model.joblib"
        encoder_path = model_dir / "encoder.joblib"

        joblib.dump(clf, model_path)
        encoder.save(encoder_path)

        self.stdout.write(self.style.SUCCESS(f"Imitation Model saved to {model_path}"))