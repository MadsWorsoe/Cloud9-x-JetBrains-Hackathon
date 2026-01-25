from django.core.management.base import BaseCommand
import numpy as np
from pathlib import Path
from matches.models import Game
from draft.models import DraftAction, TeamChampionPickStats, TeamChampionBanStats
from draft.machine_learning.encoder import DraftModelEncoder
import joblib
from sklearn.ensemble import GradientBoostingClassifier
import random

class Command(BaseCommand):
    help = "Train the Draft Model using Gradient Boosting"

    def handle(self, *args, **options):
        # 1. Initialize and Fit Encoder
        self.stdout.write("Initializing Encoder from DB...")
        encoder = DraftModelEncoder().fit()
        num_champs = encoder.num_champions
        num_teams = encoder.num_teams

        # 2. Cache Stats
        self.stdout.write("Caching Team Champion Stats...")
        stats_cache = {}
        all_stats = TeamChampionPickStats.objects.all().values('team_id', 'champion_id', 'wins', 'games_played')
        for s in all_stats:
            wr = (s['wins'] + 1) / (s['games_played'] + 2)
            stats_cache[(str(s['team_id']), str(s['champion_id']))] = wr

        ban_stats_cache = {}
        all_ban_stats = TeamChampionBanStats.objects.all().values('team_id', 'champion_id', 'wins', 'games_banned')
        for s in all_ban_stats:
            wr = (s['wins'] + 1) / (s['games_banned'] + 2)
            ban_stats_cache[(str(s['team_id']), str(s['champion_id']))] = wr

        # 3. Fetch Games
        games = Game.objects.filter(winning_team__isnull=False).select_related('team_1', 'team_2', 'winning_team')
        self.stdout.write(f"Processing {games.count()} games...")

        X_data = []
        y_data = []

        def get_comp_wr(team_id, champ_ids):
            if not champ_ids: return 0.5
            total = 0
            for cid in champ_ids:
                key = (str(team_id), str(cid))
                total += stats_cache.get(key, 0.5)
            return total / len(champ_ids)

        def get_ban_wr(team_id, champ_ids):
            if not champ_ids: return 0.5
            total = 0
            for cid in champ_ids:
                key = (str(team_id), str(cid))
                total += ban_stats_cache.get(key, 0.5)
            return total / len(champ_ids)

        # 4. Build Dataset
        self.stdout.write("Building dataset...")
        for game in games.iterator():
            if game.team_1_side == 'blue':
                blue_id, red_id = game.team_1_id, game.team_2_id
            else:
                blue_id, red_id = game.team_2_id, game.team_1_id

            winning_side = 1 if game.winning_team_id == blue_id else 0
            
            all_actions = list(DraftAction.objects.filter(game=game).order_by('sequence_number'))

            # Data Augmentation: snapshots of the draft
            for i in range(2, len(all_actions) + 1):
                current_slice = all_actions[:i]
                
                b_p = [a.champion_id for a in current_slice if a.team_side == 'blue' and a.action_type == 'pick']
                r_p = [a.champion_id for a in current_slice if a.team_side == 'red' and a.action_type == 'pick']
                b_b = [a.champion_id for a in current_slice if a.team_side == 'blue' and a.action_type == 'ban']
                r_b = [a.champion_id for a in current_slice if a.team_side == 'red' and a.action_type == 'ban']

                # --- FEATURE VECTOR CONSTRUCTION ---
                # Size: num_teams (Blue) + num_teams (Red) + num_champs (Blue) + num_champs (Red) + Stats
                
                # 1. Team Identity (One-Hot)
                blue_team_vec = np.zeros(num_teams)
                red_team_vec = np.zeros(num_teams)
                
                b_t_id = encoder.get_team_id(blue_id)
                r_t_id = encoder.get_team_id(red_id)
                
                if b_t_id < num_teams: blue_team_vec[b_t_id] = 1
                if r_t_id < num_teams: red_team_vec[r_t_id] = 1

                # 2. Champion Presence
                blue_presence = np.zeros(num_champs)
                red_presence = np.zeros(num_champs)
                
                for cid in b_p:
                    idx = encoder.get_champ_ids([cid])[0]
                    if idx < num_champs: blue_presence[idx] = 1
                
                for cid in r_p:
                    idx = encoder.get_champ_ids([cid])[0]
                    if idx < num_champs: red_presence[idx] = 1

                # Stats Features
                b_wr = get_comp_wr(blue_id, b_p)
                r_wr = get_comp_wr(red_id, r_p)
                b_ban_wr = get_ban_wr(blue_id, b_b)
                r_ban_wr = get_ban_wr(red_id, r_b)

                stats_vector = [
                    b_wr, r_wr, b_wr - r_wr,
                    b_ban_wr, r_ban_wr, b_ban_wr - r_ban_wr,
                    i / 20.0,
                    len(b_p) / 5.0,
                    len(r_p) / 5.0,
                    0.0, 0.0, 0.0 # Padding for consistency
                ]
                
                full_row = np.concatenate([blue_team_vec, red_team_vec, blue_presence, red_presence, stats_vector])
                X_data.append(full_row)
                y_data.append(winning_side)

        # 5. Train
        # Shuffle
        combined = list(zip(X_data, y_data))
        random.shuffle(combined)
        X_data, y_data = zip(*combined)
        
        X_data = np.array(X_data)
        y_data = np.array(y_data)
        
        self.stdout.write(f"Training Gradient Boosting Model on {len(X_data)} samples with {X_data.shape[1]} features...")
        
        # GradientBoostingClassifier is robust to unscaled data and sparse features
        clf = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42)
        clf.fit(X_data, y_data)
        
        acc = clf.score(X_data, y_data)
        self.stdout.write(f"Training Accuracy: {acc:.4f}")

        # 6. Save Artifacts
        model_dir = Path("draft/ml_artifacts")
        model_dir.mkdir(exist_ok=True, parents=True)
        
        model_path = model_dir / "draft_xgb_model.joblib"
        encoder_path = model_dir / "encoder.joblib"
        
        joblib.dump(clf, model_path)
        encoder.save(encoder_path)
        
        self.stdout.write(self.style.SUCCESS(f"XGB/GB Model saved to {model_path}"))
