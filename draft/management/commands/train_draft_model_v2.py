from django.core.management.base import BaseCommand
import numpy as np
from pathlib import Path
from matches.models import Game
from draft.models import DraftAction, Champion
from draft.machine_learning.encoder import DraftModelEncoder
from draft.machine_learning.features_v2 import DraftFeatureExtractor
import joblib
from sklearn.ensemble import GradientBoostingClassifier
import random

from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = "Train the V2 Draft Model with Time-Decay Sample Weights"

    def handle(self, *args, **options):
        # 1. Initialize
        self.stdout.write("Initializing...")
        encoder = DraftModelEncoder().fit()
        extractor = DraftFeatureExtractor()
        num_champs = encoder.num_champions
        
        now = timezone.now()
        half_life_days = 180.0
        
        # 2. Fetch Games
        games = Game.objects.filter(winning_team__isnull=False).select_related('match')
        self.stdout.write(f"Processing {games.count()} games...")

        X_data = []
        y_data = []
        sample_weights = []

        for game in games:
            # Calculate Weight
            game_time = game.match.start_time if game.match and game.match.start_time else (now - timedelta(days=365))
            days_diff = (now - game_time).days
            weight = 0.5 ** (days_diff / half_life_days)

            # Determine Blue/Red side winners
            blue_won = game.winning_team_id == (game.team_1_id if game.team_1_side == 'blue' else game.team_2_id)
            
            # Players (for player WR features)
            blue_players = [
                game.team_1_top_player_name, game.team_1_jungle_player_name,
                game.team_1_mid_player_name, game.team_1_bot_player_name,
                game.team_1_support_player_name
            ] if game.team_1_side == 'blue' else [
                game.team_2_top_player_name, game.team_2_jungle_player_name,
                game.team_2_mid_player_name, game.team_2_bot_player_name,
                game.team_2_support_player_name
            ]
            red_players = [
                game.team_1_top_player_name, game.team_1_jungle_player_name,
                game.team_1_mid_player_name, game.team_1_bot_player_name,
                game.team_1_support_player_name
            ] if game.team_1_side == 'red' else [
                game.team_2_top_player_name, game.team_2_jungle_player_name,
                game.team_2_mid_player_name, game.team_2_bot_player_name,
                game.team_2_support_player_name
            ]
            
            all_actions = list(DraftAction.objects.filter(game=game).order_by('sequence_number'))
            if not all_actions: continue

            # Get Advanced Features
            blue_team_id = game.team_1_id if game.team_1_side == 'blue' else game.team_2_id
            red_team_id = game.team_2_id if game.team_1_side == 'blue' else game.team_1_id

            # Snapshots for augmentation
            for i in range(10, len(all_actions) + 1): # Only start from mid-draft
                current_slice = all_actions[:i]
                
                b_p = [a.champion.name for a in current_slice if a.team_side == 'blue' and a.action_type == 'pick']
                r_p = [a.champion.name for a in current_slice if a.team_side == 'red' and a.action_type == 'pick']
                
                # Get Advanced Features
                feat_vec = extractor.get_feature_vector(
                    b_p, r_p, 
                    blue_team_id=blue_team_id,
                    red_team_id=red_team_id,
                    blue_players=blue_players, 
                    red_players=red_players
                )
                
                # Get Presence Features (optional but good for context)
                b_presence = np.zeros(num_champs)
                r_presence = np.zeros(num_champs)
                for name in b_p:
                    c_id = Champion.objects.filter(name=name).first().id
                    idx = encoder.champ_map.get(str(c_id), 0)
                    if idx: b_presence[idx] = 1
                for name in r_p:
                    c_id = Champion.objects.filter(name=name).first().id
                    idx = encoder.champ_map.get(str(c_id), 0)
                    if idx: r_presence[idx] = 1
                
                # Add Team IDs as features (one-hot or embedding-like if we had them, but for GB numerical is okay-ish or we can one-hot)
                # For now let's just use the team index from encoder
                b_team_idx = encoder.get_team_id(blue_team_id)
                r_team_idx = encoder.get_team_id(red_team_id)
                team_vec = np.array([b_team_idx, r_team_idx])

                full_row = np.concatenate([feat_vec, b_presence, r_presence, team_vec])
                X_data.append(full_row)
                y_data.append(1 if blue_won else 0)
                sample_weights.append(weight)

        # 3. Train
        X_data = np.array(X_data)
        y_data = np.array(y_data)
        sample_weights = np.array(sample_weights)
        
        self.stdout.write(f"Training on {len(X_data)} samples with time-decay weights...")
        clf = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)
        clf.fit(X_data, y_data, sample_weight=sample_weights)
        
        self.stdout.write(f"Accuracy: {clf.score(X_data, y_data):.4f}")
        
        # 4. Save
        model_dir = Path("draft/ml_artifacts")
        joblib.dump(clf, model_dir / "draft_model_v2.joblib")
        self.stdout.write(self.style.SUCCESS("Saved model_v2.joblib"))
