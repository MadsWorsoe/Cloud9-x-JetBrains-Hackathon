from django.core.management.base import BaseCommand
from draft.models import Champion
from draft.machine_learning.encoder import DraftModelEncoder
from draft.machine_learning.features_v2 import DraftFeatureExtractor
import joblib
import numpy as np
from pathlib import Path
import json

class Command(BaseCommand):
    help = "Recommend optimal draft picks and bans in real-time with Role Constraints"

    def add_arguments(self, parser):
        parser.add_argument('--blue_picks', type=str, nargs='*', default=[], help="List of blue champion names")
        parser.add_argument('--red_picks', type=str, nargs='*', default=[], help="List of red champion names")
        parser.add_argument('--blue_bans', type=str, nargs='*', default=[], help="List of blue ban names")
        parser.add_argument('--red_bans', type=str, nargs='*', default=[], help="List of red ban names")
        parser.add_argument('--side', type=str, choices=['blue', 'red'], required=True, help="Which side are you on?")
        parser.add_argument('--action', type=str, choices=['pick', 'ban'], required=True, help="Are you picking or banning?")
        parser.add_argument('--blue_players', type=str, nargs='*', default=[], help="List of blue player names")
        parser.add_argument('--red_players', type=str, nargs='*', default=[], help="List of red player names")
        parser.add_argument('--blue_team_id', type=str, default=None, help="UUID of blue team")
        parser.add_argument('--red_team_id', type=str, default=None, help="UUID of red team")

    def handle(self, *args, **options):
        # 1. Load Artifacts
        model_path = Path("draft/ml_artifacts/draft_model_v2.joblib")
        roles_path = Path("draft/ml_artifacts/champ_roles.json")
        
        if not model_path.exists():
             self.stderr.write("Model v2 not found. Run train_draft_model_v2.")
             return
             
        clf = joblib.load(model_path)
        encoder = DraftModelEncoder().load(Path("draft/ml_artifacts/encoder.joblib"))
        extractor = DraftFeatureExtractor()
        
        if roles_path.exists():
            with open(roles_path, "r") as f:
                champ_roles = json.load(f)
        else:
            champ_roles = {}
        
        def can_assign_roles(champs):
            all_roles = ['top', 'jungle', 'mid', 'bot', 'support']
            def backtrack(remaining_champs, available_roles):
                if not remaining_champs: return True
                c = remaining_champs[0]
                c_possible = champ_roles.get(c, all_roles)
                for r in c_possible:
                    if r in available_roles:
                        if backtrack(remaining_champs[1:], [role for role in available_roles if role != r]):
                            return True
                return False
            return backtrack(champs, all_roles)
        
        blue_picks = options['blue_picks']
        red_picks = options['red_picks']
        blue_bans = options['blue_bans']
        red_bans = options['red_bans']
        side = options['side']
        action = options['action']
        blue_players = options['blue_players']
        red_players = options['red_players']
        blue_team_id = options['blue_team_id']
        red_team_id = options['red_team_id']

        taken_names = set(blue_picks + red_picks + blue_bans + red_bans)
        all_champions = Champion.objects.all()
        
        recommendations = []
        
        self.stdout.write(f"Analyzing {action} for {side}...")

        # Pre-calculate team indices
        b_team_idx = encoder.get_team_id(blue_team_id) if blue_team_id else 0
        r_team_idx = encoder.get_team_id(red_team_id) if red_team_id else 0
        team_vec = np.array([b_team_idx, r_team_idx])

        for champ in all_champions:
            if champ.name in taken_names: continue
            
            # Simulate state after this action
            sim_blue_picks = list(blue_picks)
            sim_red_picks = list(red_picks)
            
            if action == 'pick':
                if side == 'blue': sim_blue_picks.append(champ.name)
                else: sim_red_picks.append(champ.name)
            else:
                # For bans, we evaluate "How much does banning this help us?"
                # One way is to see how much it would hurt us if the OPPONENT picked it.
                # So we simulate the opponent picking it and see the win prob.
                # A high win prob for them means we should probably ban it.
                if side == 'blue': sim_red_picks.append(champ.name)
                else: sim_blue_picks.append(champ.name)

            # Build Feature Vector
            feat_vec = extractor.get_feature_vector(
                sim_blue_picks, sim_red_picks,
                blue_team_id=blue_team_id,
                red_team_id=red_team_id,
                blue_players=blue_players,
                red_players=red_players
            )
            
            # Presence
            b_presence = np.zeros(encoder.num_champions)
            r_presence = np.zeros(encoder.num_champions)
            for name in sim_blue_picks:
                c_id = Champion.objects.filter(name=name).first().id
                idx = encoder.champ_map.get(str(c_id), 0)
                if idx: b_presence[idx] = 1
            for name in sim_red_picks:
                c_id = Champion.objects.filter(name=name).first().id
                idx = encoder.champ_map.get(str(c_id), 0)
                if idx: r_presence[idx] = 1
            
            full_row = np.concatenate([feat_vec, b_presence, r_presence, team_vec])
            
            # Predict
            # proba is [P(Red wins), P(Blue wins)] or vice versa?
            # In train_draft_model_v2, y=1 if blue_won. So [P(Red), P(Blue)]
            win_probs = clf.predict_proba([full_row])[0]
            blue_win_prob = win_probs[1]
            
            if action == 'pick':
                score = blue_win_prob if side == 'blue' else (1 - blue_win_prob)
            else:
                # Ban score: How much does it REDUCE opponent win prob?
                # Opponent win prob if they picked it:
                opp_win_prob = (1 - blue_win_prob) if side == 'blue' else blue_win_prob
                score = opp_win_prob # Higher score = better ban (prevents a strong opponent pick)

            recommendations.append((champ.name, score))

        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        self.stdout.write(f"\nTop 5 {action} recommendations for {side}:")
        for name, score in recommendations[:5]:
            self.stdout.write(f"- {name}: {score:.2%}")
