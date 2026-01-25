from django.core.management.base import BaseCommand
from matches.models import Team, Player
from draft.models import Champion
from draft.machine_learning.encoder import DraftModelEncoder
from draft.machine_learning.features_v2 import DraftFeatureExtractor
import joblib
import numpy as np
from pathlib import Path
import json

class Command(BaseCommand):
    help = "Simulates a full draft using the V2 Win Prediction Model with Role Constraints"

    def add_arguments(self, parser):
        parser.add_argument('--blue', type=str, default="T1", help="Name of Blue Team")
        parser.add_argument('--red', type=str, default="Gen.G", help="Name of Red Team")
        parser.add_argument('--verbose', action='store_true', help="Print top 3 choices for each step")

    def handle(self, *args, **options):
        # 1. Load Artifacts
        model_path = Path("draft/ml_artifacts/draft_model_v2.joblib")
        encoder_path = Path("draft/ml_artifacts/encoder.joblib")
        roles_path = Path("draft/ml_artifacts/champ_roles.json")
        
        if not model_path.exists():
            self.stderr.write("Model v2 not found. Run train_draft_model_v2.")
            return

        if not roles_path.exists():
            self.stderr.write("Roles mapping not found. Run calculate_champ_roles.")
            return

        self.stdout.write("Loading V2 Draft Model and Roles...")
        clf = joblib.load(model_path)
        encoder = DraftModelEncoder().load(encoder_path)
        extractor = DraftFeatureExtractor()
        
        with open(roles_path, "r") as f:
            champ_roles = json.load(f)
        
        def can_assign_roles(champs):
            """Returns True if the list of champions can be assigned to 5 unique roles."""
            all_roles = ['top', 'jungle', 'mid', 'bot', 'support']
            
            def backtrack(remaining_champs, available_roles):
                if not remaining_champs:
                    return True
                
                c = remaining_champs[0]
                # If champ is not in map, we assume it's a 'wildcard' for now, 
                # but better to assume it can play anything it was ever played in.
                c_possible = champ_roles.get(c, all_roles)
                
                for r in c_possible:
                    if r in available_roles:
                        if backtrack(remaining_champs[1:], [role for role in available_roles if role != r]):
                            return True
                return False
            
            return backtrack(champs, all_roles)

        blue_name_query = options['blue']
        red_name_query = options['red']
        verbose = options['verbose']
        
        blue_team = Team.objects.filter(name__icontains=blue_name_query).first()
        red_team = Team.objects.filter(name__icontains=red_name_query).first()
        
        if not blue_team or not red_team:
            self.stderr.write("Teams not found.")
            return
            
        # Get players for player-pool features
        blue_players = list(Player.objects.filter(team=blue_team).values_list('name', flat=True))
        red_players = list(Player.objects.filter(team=red_team).values_list('name', flat=True))
        
        self.stdout.write(f"\n🔵 BLUE: {blue_team.name} ({len(blue_players)} players)")
        self.stdout.write(f"🔴 RED: {red_team.name} ({len(red_players)} players)\n")

        # Pre-calculate team indices
        b_team_idx = encoder.get_team_id(blue_team.id)
        r_team_idx = encoder.get_team_id(red_team.id)
        team_vec = np.array([b_team_idx, r_team_idx])

        # Draft State (Names)
        blue_picks = []
        red_picks = []
        blue_bans = []
        red_bans = []
        
        phases = [
            ("Blue Ban 1", "blue", "ban"), ("Red Ban 1", "red", "ban"),
            ("Blue Ban 2", "blue", "ban"), ("Red Ban 2", "red", "ban"),
            ("Blue Ban 3", "blue", "ban"), ("Red Ban 3", "red", "ban"),
            ("Blue Pick 1", "blue", "pick"), ("Red Pick 1", "red", "pick"), 
            ("Red Pick 2", "red", "pick"), ("Blue Pick 2", "blue", "pick"), 
            ("Blue Pick 3", "blue", "pick"), ("Red Pick 3", "red", "pick"),
            ("Red Ban 4", "red", "ban"), ("Blue Ban 4", "blue", "ban"),
            ("Red Ban 5", "red", "ban"), ("Blue Ban 5", "blue", "ban"),
            ("Red Pick 4", "red", "pick"), ("Blue Pick 4", "blue", "pick"),
            ("Blue Pick 5", "blue", "pick"), ("Red Pick 5", "red", "pick"),
        ]

        all_champions = list(Champion.objects.all())
        name_to_idx = {c.name: encoder.champ_map.get(str(c.id), 0) for c in all_champions}

        for i_phase, (phase_name, side, action) in enumerate(phases):
            taken_names = set(blue_picks + red_picks + blue_bans + red_bans)
            candidates = []

            for champ in all_champions:
                if champ.name in taken_names: continue
                
                # Simulate state after this action
                sim_blue_picks = list(blue_picks)
                sim_red_picks = list(red_picks)
                
                if action == 'pick':
                    if side == 'blue': 
                        sim_blue_picks.append(champ.name)
                        if not can_assign_roles(sim_blue_picks): continue
                    else: 
                        sim_red_picks.append(champ.name)
                        if not can_assign_roles(sim_red_picks): continue
                else:
                    # Ban evaluation: How dangerous if the OPPONENT picks it?
                    if side == 'blue': 
                        sim_red_picks.append(champ.name)
                        if not can_assign_roles(sim_red_picks): continue
                    else: 
                        sim_blue_picks.append(champ.name)
                        if not can_assign_roles(sim_blue_picks): continue

                # Build Feature Vector
                feat_vec = extractor.get_feature_vector(
                    sim_blue_picks, sim_red_picks,
                    blue_team_id=blue_team.id,
                    red_team_id=red_team.id,
                    blue_players=blue_players,
                    red_players=red_players
                )
                
                # Presence Features
                b_presence = np.zeros(encoder.num_champions)
                r_presence = np.zeros(encoder.num_champions)
                for name in sim_blue_picks:
                    idx = name_to_idx.get(name, 0)
                    if idx: b_presence[idx] = 1
                for name in sim_red_picks:
                    idx = name_to_idx.get(name, 0)
                    if idx: r_presence[idx] = 1
                
                full_row = np.concatenate([feat_vec, b_presence, r_presence, team_vec])
                
                # Predict
                win_probs = clf.predict_proba([full_row])[0]
                blue_win_prob = win_probs[1]
                
                if action == 'pick':
                    score = blue_win_prob if side == 'blue' else (1 - blue_win_prob)
                else:
                    # Ban score: How much does it REDUCE opponent win prob?
                    opp_win_prob = (1 - blue_win_prob) if side == 'blue' else blue_win_prob
                    score = opp_win_prob

                candidates.append((champ.name, score, blue_win_prob))

            candidates.sort(key=lambda x: x[1], reverse=True)
            best_name, best_score, best_blue_wp = candidates[0]

            # Commit
            if side == 'blue':
                if action == 'pick': blue_picks.append(best_name)
                else: blue_bans.append(best_name)
            else:
                if action == 'pick': red_picks.append(best_name)
                else: red_bans.append(best_name)

            # Print progress
            self.stdout.write(f"[{phase_name}] {side.upper()} {action}: {best_name} (Blue WP: {best_blue_wp:.1%})")
            if verbose:
                for name, score, wp in candidates[1:3]:
                    self.stdout.write(f"  - alt: {name} (Score: {score:.2f})")

        def get_role_assignment(champs):
            all_roles = ['top', 'jungle', 'mid', 'bot', 'support']
            def backtrack(remaining_champs, available_roles, current_assignment):
                if not remaining_champs:
                    return True
                c = remaining_champs[0]
                c_possible = champ_roles.get(c, all_roles)
                for r in c_possible:
                    if r in available_roles:
                        current_assignment[c] = r
                        if backtrack(remaining_champs[1:], [role for role in available_roles if role != r], current_assignment):
                            return True
                        # No need to del since we return True or continue
                return False
            res = {}
            backtrack(champs, all_roles, res)
            return res

        self.stdout.write("\n=== SIMULATION COMPLETE ===")
        blue_assignments = get_role_assignment(blue_picks)
        red_assignments = get_role_assignment(red_picks)

        self.stdout.write(f"\n🔵 {blue_team.name} Draft:")
        blue_picks_str = [f"{c} ({blue_assignments.get(c, 'unknown')})" for c in blue_picks]
        self.stdout.write(f"Picks: {', '.join(blue_picks_str)}")
        self.stdout.write(f"Bans: {', '.join(blue_bans)}")

        self.stdout.write(f"\n🔴 {red_team.name} Draft:")
        red_picks_str = [f"{c} ({red_assignments.get(c, 'unknown')})" for c in red_picks]
        self.stdout.write(f"Picks: {', '.join(red_picks_str)}")
        self.stdout.write(f"Bans: {', '.join(red_bans)}")
        
        # Final Win Prob
        final_feat = extractor.get_feature_vector(blue_picks, red_picks, blue_players=blue_players, red_players=red_players)
        b_pres = np.zeros(encoder.num_champions)
        r_pres = np.zeros(encoder.num_champions)
        for name in blue_picks: b_pres[name_to_idx.get(name, 0)] = 1
        for name in red_picks: r_pres[name_to_idx.get(name, 0)] = 1
        final_row = np.concatenate([final_feat, b_pres, r_pres])
        final_wp = clf.predict_proba([final_row])[0][1]
        
        self.stdout.write(f"\nPredicted Win Probability for BLUE ({blue_team.name}): {final_wp:.1%}\n")
