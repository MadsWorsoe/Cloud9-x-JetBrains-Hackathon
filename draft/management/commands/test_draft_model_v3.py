import torch
import os
import json
from django.core.management.base import BaseCommand
from draft.machine_learning.model_v2 import DraftTransformerModel
from draft.machine_learning.analyzer_v2 import DeltaAnalyzerV2
from draft.models import Champion

class Command(BaseCommand):
    help = "Test and simulate drafts with the new model (V3)"

    def add_arguments(self, parser):
        parser.add_argument('team_blue', type=str, nargs='?', default=None, help='Name or External ID of Blue Team')
        parser.add_argument('team_red', type=str, nargs='?', default=None, help='Name or External ID of Red Team')
        parser.add_argument('--team', type=str, default=None, help='External ID of the team (for single-step test)')
        parser.add_argument('--stochastic', action='store_true', help='Sample picks probabilistically')

    def get_team_idx(self, team_name_or_id, team_to_idx):
        if not team_name_or_id:
            return 0
        from matches.models import Team
        from draft.models import DraftAction
        from django.db.models import Q

        team = None
        if team_name_or_id in team_to_idx:
            try:
                team = Team.objects.get(external_id=team_name_or_id)
            except Team.DoesNotExist:
                pass
        
        if not team:
            try:
                team = Team.objects.get(name=team_name_or_id)
            except (Team.DoesNotExist, Team.MultipleObjectsReturned):
                # If multiple, try to find one with draft actions
                if Team.objects.filter(name=team_name_or_id).exists():
                    teams = Team.objects.filter(name=team_name_or_id)
                    for t in teams:
                        if DraftAction.objects.filter(Q(game__team_1=t) | Q(game__team_2=t)).exists():
                            team = t
                            break
                    if not team:
                        team = teams[0]

        if not team:
            return None
        
        # Check if team has draft actions
        has_actions = DraftAction.objects.filter(
            Q(game__team_1=team) | Q(game__team_2=team)
        ).exists()
        
        if not has_actions:
             return None
             
        return team_to_idx.get(team.external_id, 0)

    def handle(self, *args, **options):
        artifacts_dir = "draft/ml_artifacts"
        model_path = os.path.join(artifacts_dir, "draft_model_v3.pth")
        mapping_path = os.path.join(artifacts_dir, "draft_mappings_v3.json")
        
        if not os.path.exists(model_path) or not os.path.exists(mapping_path):
            self.stderr.write("Model or mappings not found. Please run train_draft_model_v3 first.")
            return

        with open(mapping_path, 'r') as f:
            mappings = json.load(f)
            
        champ_to_idx = mappings["champ_to_idx"]
        idx_to_name = mappings["idx_to_name"]
        num_champions = mappings["num_champions"]
        num_teams = mappings["num_teams"]
        team_to_idx = mappings["team_to_idx"]
        
        model = DraftTransformerModel(num_champions=num_champions, num_teams=num_teams)
        model.load_state_dict(torch.load(model_path))
        model.eval()
        
        analyzer = DeltaAnalyzerV2(
            model, champ_to_idx, mappings["idx_to_champ"], idx_to_name, 
            os.path.join(artifacts_dir, "champ_roles.json")
        )

        if options['team_blue'] and options['team_red']:
            blue_idx = self.get_team_idx(options['team_blue'], team_to_idx)
            red_idx = self.get_team_idx(options['team_red'], team_to_idx)
            
            if blue_idx is None or red_idx is None:
                if blue_idx is None:
                    self.stderr.write(f"Team '{options['team_blue']}' not found or has no draft actions.")
                if red_idx is None:
                    self.stderr.write(f"Team '{options['team_red']}' not found or has no draft actions.")
                
                from matches.models import Team
                from django.db.models import Q
                self.stdout.write("\nTop 10 valid teams with draft actions:")
                valid_teams = Team.objects.filter(
                    Q(team_1_game__draft_actions__isnull=False) | 
                    Q(team_2_game__draft_actions__isnull=False)
                ).distinct().order_by('name')[:10]
                for vt in valid_teams:
                    self.stdout.write(f" - {vt.name} ({vt.external_id})")
                return

            self.simulate_full_draft(options, model, analyzer, champ_to_idx, idx_to_name, team_to_idx, num_champions, blue_idx, red_idx)
        else:
            self.run_single_step_test(options, model, analyzer, champ_to_idx, idx_to_name, team_to_idx, num_champions)

    def simulate_full_draft(self, options, model, analyzer, champ_to_idx, idx_to_name, team_to_idx, num_champions, blue_team_idx, red_team_idx):
        from draft.ml.constants import DRAFT_PHASES
        
        self.stdout.write(f"Simulating draft: {options['team_blue']} (Blue) vs {options['team_red']} (Red)")
        
        champ_ids = torch.full((1, 20), num_champions, dtype=torch.long)
        action_types = torch.zeros((1, 20), dtype=torch.long)
        sides = torch.zeros((1, 20), dtype=torch.long)
        positions = torch.arange(20).unsqueeze(0)
        
        history = []
        
        for step, (side, act) in enumerate(DRAFT_PHASES):
            curr_team_idx = blue_team_idx if side == 'blue' else red_team_idx
            opp_team_idx = red_team_idx if side == 'blue' else blue_team_idx
            
            with torch.no_grad():
                logits = model(champ_ids, action_types, sides, positions, torch.tensor([curr_team_idx]), torch.tensor([opp_team_idx]))
                probs = torch.softmax(logits, dim=-1)[0]
            
            # Mask used champions
            mask = torch.ones_like(probs)
            for i in range(20):
                val = champ_ids[0, i].item()
                if val < num_champions:
                    mask[val] = 0
            
            probs = probs * mask

            # Apply role penalty if it's a pick
            if act == "pick":
                current_team_picks = [h[0] for h in history if h[1] == "pick" and h[2] == side]
                for i in range(num_champions):
                    if probs[i] > 0:
                        champ_name = idx_to_name[str(i)]
                        if not analyzer.is_viable_pick(current_team_picks, champ_name):
                            # Soft penalty
                            probs[i] *= 0.01

            if probs.sum() == 0:
                self.stderr.write(f"No valid champions left at step {step}")
                break
                
            top_k = torch.topk(probs, 3)
            
            if options['stochastic']:
                next_champ_idx = torch.multinomial(probs, 1).item()
            else:
                next_champ_idx = top_k.indices[0].item()
                
            champ_name = idx_to_name[str(next_champ_idx)]
            
            # Update state
            champ_ids[0, step] = next_champ_idx
            action_types[0, step] = 1 if act == "ban" else 2
            sides[0, step] = 1 if side == "blue" else 2
            
            history.append((champ_name, act, side))
            
            color = "\033[94m" if side == "blue" else "\033[91m"
            reset = "\033[0m"
            self.stdout.write(f"Step {step+1:2}: {color}{side.upper():4}{reset} {act.upper():4}")
            for i in range(3):
                idx = top_k.indices[i].item()
                val = top_k.values[i].item()
                if val == 0: continue
                name = idx_to_name[str(idx)]
                mark = "->" if idx == next_champ_idx else "  "
                self.stdout.write(f"  {mark} {name:<15} ({val:.4f})")

        self.display_analysis(history, analyzer)
        self.display_final_summary(history, analyzer)

    def run_single_step_test(self, options, model, analyzer, champ_to_idx, idx_to_name, team_to_idx, num_champions):
        # Original logic
        champ_ids = torch.full((1, 20), num_champions, dtype=torch.long)
        action_types = torch.zeros((1, 20), dtype=torch.long)
        sides = torch.zeros((1, 20), dtype=torch.long)
        positions = torch.arange(20).unsqueeze(0)
        
        history = [
            ("Aatrox", "ban", "blue"),
            ("Ahri", "ban", "red"),
            ("Vi", "pick", "blue"),
            ("Lucian", "pick", "red")
        ]
        
        for i, (name, act, side) in enumerate(history):
            try:
                champ = Champion.objects.get(name=name)
                champ_ids[0, i] = champ_to_idx[champ.id]
                action_types[0, i] = 1 if act == "ban" else 2
                sides[0, i] = 1 if side == "blue" else 2
            except Champion.DoesNotExist:
                self.stderr.write(f"Champion {name} not found in DB.")
                continue

        team_idx_val = 0
        if options['team']:
            idx = self.get_team_idx(options['team'], team_to_idx)
            if idx is None:
                self.stderr.write(f"Team '{options['team']}' not found or has no draft actions.")
                return
            team_idx_val = idx
            
        team_idx = torch.tensor([team_idx_val])
        opp_team_idx = torch.tensor([0]) # Default for single step test if not specified
        
        with torch.no_grad():
            logits = model(champ_ids, action_types, sides, positions, team_idx, opp_team_idx)
            probs = torch.softmax(logits, dim=-1)[0]
            
        top_k = torch.topk(probs, 5)
        self.stdout.write("\n=== Prediction Analysis ===")
        self.stdout.write(f"Context: {len(history)} steps in draft.")
        self.stdout.write("Top 5 predicted champions for next step:")
        for i in range(5):
            idx = top_k.indices[i].item()
            name = idx_to_name[str(idx)]
            self.stdout.write(f" {i+1}. {name:<15} Prob: {top_k.values[i].item():.4f}")
            
        top_champ_idx = top_k.indices[0].item()
        delta = analyzer.compute_delta(champ_ids, action_types, sides, positions, team_idx, top_champ_idx)
        self.stdout.write(f"\nDelta for {idx_to_name[str(top_champ_idx)]}: {delta:.6f}")
        
        self.display_analysis(history, analyzer)
        self.display_final_summary(history, analyzer)

    def display_analysis(self, history, analyzer):
        self.stdout.write("\n=== Role Analysis ===")
        blue_picks = [h[0] for h in history if h[1] == "pick" and h[2] == "blue"]
        red_picks = [h[0] for h in history if h[1] == "pick" and h[2] == "red"]
        
        if blue_picks:
            self.stdout.write("BLUE Team:")
            for i, pick in enumerate(blue_picks):
                role = analyzer.get_displayed_role(blue_picks[:i], pick)
                self.stdout.write(f" - {pick:<10} assigned to {role}")
            
            pressure_blue = analyzer.get_role_pressure(blue_picks)
            p_str = ", ".join([f"{r.upper()}:{v:.1f}" for r, v in pressure_blue.items() if v > 0])
            if p_str:
                self.stdout.write(f"   Remaining Pressure: {p_str}")
        
        if red_picks:
            self.stdout.write("\nRED Team:")
            for i, pick in enumerate(red_picks):
                role = analyzer.get_displayed_role(red_picks[:i], pick)
                self.stdout.write(f" - {pick:<10} assigned to {role}")

            pressure_red = analyzer.get_role_pressure(red_picks)
            p_str = ", ".join([f"{r.upper()}:{v:.1f}" for r, v in pressure_red.items() if v > 0])
            if p_str:
                self.stdout.write(f"   Remaining Pressure: {p_str}")

    def display_final_summary(self, history, analyzer):
        blue_picks = []
        red_picks = []
        blue_bans = []
        red_bans = []
        
        for name, act, side in history:
            if act == "pick":
                if side == "blue":
                    blue_picks.append(name)
                else:
                    red_picks.append(name)
            else:
                if side == "blue":
                    blue_bans.append(name)
                else:
                    red_bans.append(name)
                    
        def get_sorted_picks(picks):
            picks_with_roles = []
            for i, pick in enumerate(picks):
                role = analyzer.get_displayed_role(picks[:i], pick)
                picks_with_roles.append((pick, role))
            
            role_order = {"TOP": 0, "JUNGLE": 1, "MID": 2, "ADC": 3, "BOT": 3, "SUPPORT": 4, "FLEX": 5, "UNKNOWN": 6}
            picks_with_roles.sort(key=lambda x: role_order.get(x[1], 99))
            return [f"{name} ({role})" for name, role in picks_with_roles]

        self.stdout.write("\n=== Final Draft ===")
        self.stdout.write(f"BLUE Picks: {get_sorted_picks(blue_picks)}")
        self.stdout.write(f"BLUE Bans: {blue_bans}")
        self.stdout.write(f"RED Picks: {get_sorted_picks(red_picks)}")
        self.stdout.write(f"RED Bans: {red_bans}")
        self.stdout.write("")
