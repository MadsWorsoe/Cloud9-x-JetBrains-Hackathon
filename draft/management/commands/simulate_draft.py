import torch
import os
import json
import numpy as np
from django.core.management.base import BaseCommand
from django.conf import settings
from matches.models import Team
from draft.models import Champion, DraftAction
from django.db.models import Q

# V2 Imports (Original PolicyNet)
from draft.ml.model import DraftPolicyNet
from draft.ml.encoder import encode_state, get_uuid_to_roles, ROLES, JSON_ROLE_TO_INTERNAL
from draft.ml.utils import find_role_assignment as find_role_assignment_v2
from draft.ml.phase import get_draft_phase
from draft.ml.constants import DRAFT_PHASES

# V3 Imports (Transformer)
from draft.machine_learning.model_v2 import DraftTransformerModel
from draft.machine_learning.analyzer_v2 import DeltaAnalyzerV2 as DeltaAnalyzerV3

class Command(BaseCommand):
    help = "Unified draft simulation command supporting multiple model versions (V2 and V3)"

    def add_arguments(self, parser):
        parser.add_argument('team_blue', type=str, help='Name or External ID of Blue Team')
        parser.add_argument('team_red', type=str, help='Name or External ID of Red Team')
        parser.add_argument('--model', type=str, default=None, help='Model version to use (v2 or v3). Defaults to settings.DRAFT_MODEL_VERSION')
        parser.add_argument('--stochastic', action='store_true', help='Sample picks probabilistically')
        parser.add_argument('--top_n', type=int, default=3, help='Show top N options per step')

    def handle(self, *args, **options):
        # Determine version from argument or settings
        version = options['model'] or getattr(settings, 'DRAFT_MODEL_VERSION', 'v3')
        version = version.lower()
        
        self.stdout.write(self.style.SUCCESS(f"=== League of Legends Draft Simulator ==="))
        self.stdout.write(f"Active Model: {version.upper()}")

        if version == 'v3':
            self.run_v3(options)
        elif version == 'v2':
            self.run_v2(options)
        else:
            self.stderr.write(f"Unknown model version: {version}. Please use 'v2' or 'v3'.")

    def get_team_obj(self, name_or_id):
        try:
            # Check for direct ID match first
            team = Team.objects.filter(Q(external_id=name_or_id) | Q(name=name_or_id)).first()
            if not team:
                return None
            return team
        except Exception:
            return None

    def run_v2(self, options):
        """Simulation logic for the V2 PolicyNet model"""
        team_blue_obj = self.get_team_obj(options["team_blue"])
        team_red_obj = self.get_team_obj(options["team_red"])

        if not team_blue_obj or not team_red_obj:
            self.stderr.write(f"Team lookup failed. Blue: {options['team_blue']}, Red: {options['team_red']}")
            return

        artifacts_dir = "draft/ml_artifacts"
        model_path = os.path.join(artifacts_dir, "draft_model.pt")
        if not os.path.exists(model_path):
            self.stderr.write(f"Model V2 weights not found at {model_path}")
            return

        checkpoint = torch.load(model_path, map_location="cpu")
        model = DraftPolicyNet(
            input_dim=checkpoint["input_dim"], 
            num_champions=checkpoint["num_champions"], 
            num_teams=checkpoint.get("num_teams", 100)
        )
        model.load_state_dict(checkpoint["model_state"])
        model.eval()

        champion_id_to_index = checkpoint["champion_id_to_index"]
        team_id_to_index = checkpoint.get("team_id_to_index", {})
        index_to_champion_id = {v: k for k, v in champion_id_to_index.items()}

        blue_team_idx = team_id_to_index.get(team_blue_obj.external_id, 0)
        red_team_idx = team_id_to_index.get(team_red_obj.external_id, 0)

        blue_picks, red_picks, blue_bans, red_bans = [], [], [], []
        history = []

        self.stdout.write(f"Simulating: {team_blue_obj.name} vs {team_red_obj.name}\n")

        for step_num, (side, action_type) in enumerate(DRAFT_PHASES):
            curr_team_idx = blue_team_idx if side.lower() == "blue" else red_team_idx
            opp_team_idx = red_team_idx if side.lower() == "blue" else blue_team_idx
            phase = get_draft_phase(step_num)

            own_picks = blue_picks if side.lower() == "blue" else red_picks
            enemy_picks = red_picks if side.lower() == "blue" else blue_picks

            state = encode_state(
                own_picks=[index_to_champion_id[i] for i in own_picks],
                enemy_picks=[index_to_champion_id[i] for i in enemy_picks],
                banned_champions=[index_to_champion_id[i] for i in blue_bans + red_bans],
                side=side,
                phase=phase,
                team_idx=curr_team_idx,
                champion_id_to_index=champion_id_to_index
            )

            x_vec = np.concatenate([state["own_picks"], state["enemy_picks"], state["bans"], state["side"], state["phase"], state["role_pressure"]])
            x_tensor = torch.tensor(x_vec, dtype=torch.float32).unsqueeze(0)
            
            with torch.no_grad():
                logits = model(x_tensor, torch.tensor([curr_team_idx]), torch.tensor([opp_team_idx]))
                probs = torch.softmax(logits, dim=1).squeeze(0).numpy()

            # Mask used
            probs[blue_picks + red_picks + blue_bans + red_bans] = 0
            
            # Role penalty
            if action_type.upper() == "PICK":
                mapping = get_uuid_to_roles()
                curr_team_roles = []
                for p_idx in own_picks:
                    roles = mapping.get(index_to_champion_id[p_idx], [])
                    curr_team_roles.append([JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in roles if JSON_ROLE_TO_INTERNAL.get(r.lower())])

                for i in range(len(probs)):
                    if probs[i] > 0:
                        c_uuid = index_to_champion_id[i]
                        c_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in mapping.get(c_uuid, []) if JSON_ROLE_TO_INTERNAL.get(r.lower())]
                        if c_roles and not find_role_assignment_v2(curr_team_roles + [c_roles]):
                            probs[i] *= 0.01

            if probs.sum() == 0: break
            probs /= probs.sum()

            top_idx = int(np.argmax(probs))
            pick_idx = int(np.random.choice(len(probs), p=probs)) if options['stochastic'] else top_idx
            
            champ_obj = Champion.objects.get(id=index_to_champion_id[pick_idx])
            champ_name = champ_obj.name
            
            if action_type.lower() == "pick":
                if side.lower() == "blue": blue_picks.append(pick_idx)
                else: red_picks.append(pick_idx)
            else:
                if side.lower() == "blue": blue_bans.append(pick_idx)
                else: red_bans.append(pick_idx)

            color = "\033[94m" if side.lower() == "blue" else "\033[91m"
            self.stdout.write(f"Step {step_num+1:2}: {color}{side.upper():4}\033[0m {action_type.upper():4} -> {champ_name}")
            history.append((champ_name, action_type.lower(), side.lower()))

        def v2_sorter(picks):
            # Simple sorting by name since V2 doesn't have an analyzer with easy role mapping
            return sorted(picks)

        self.display_summary(history, role_sorter=v2_sorter)

    def run_v3(self, options):
        """Simulation logic for the V3 Transformer model"""
        artifacts_dir = "draft/ml_artifacts"
        model_path = os.path.join(artifacts_dir, "draft_model_v3.pth")
        mapping_path = os.path.join(artifacts_dir, "draft_mappings_v3.json")
        
        if not os.path.exists(model_path) or not os.path.exists(mapping_path):
            self.stderr.write("V3 Model artifacts not found. Run training first.")
            return

        with open(mapping_path, 'r') as f:
            mappings = json.load(f)
            
        champ_to_idx = mappings["champ_to_idx"]
        idx_to_name = mappings["idx_to_name"]
        num_champions = mappings["num_champions"]
        team_to_idx = mappings["team_to_idx"]
        
        model = DraftTransformerModel(num_champions=num_champions, num_teams=mappings["num_teams"])
        model.load_state_dict(torch.load(model_path, map_location="cpu"))
        model.eval()
        
        analyzer = DeltaAnalyzerV3(model, champ_to_idx, mappings["idx_to_champ"], idx_to_name, os.path.join(artifacts_dir, "champ_roles.json"))

        team_blue = self.get_team_obj(options["team_blue"])
        team_red = self.get_team_obj(options["team_red"])
        
        if not team_blue or not team_red:
            self.stderr.write("One or both teams not found.")
            return

        blue_idx = team_to_idx.get(team_blue.external_id, 0)
        red_idx = team_to_idx.get(team_red.external_id, 0)

        champ_ids = torch.full((1, 20), num_champions, dtype=torch.long)
        action_types = torch.zeros((1, 20), dtype=torch.long)
        sides = torch.zeros((1, 20), dtype=torch.long)
        positions = torch.arange(20).unsqueeze(0)
        
        history = []
        self.stdout.write(f"Simulating: {team_blue.name} vs {team_red.name}\n")

        for step, (side, act) in enumerate(DRAFT_PHASES):
            curr_team_idx = blue_idx if side == 'blue' else red_idx
            opp_team_idx = red_idx if side == 'blue' else blue_idx
            with torch.no_grad():
                logits = model(champ_ids, action_types, sides, positions, torch.tensor([curr_team_idx]), torch.tensor([opp_team_idx]))
                probs = torch.softmax(logits, dim=-1)[0]
            
            mask = torch.ones_like(probs)
            for i in range(20):
                val = champ_ids[0, i].item()
                if val < num_champions: mask[val] = 0
            probs = probs * mask

            if act == "pick":
                current_team_picks = [h[0] for h in history if h[1] == "pick" and h[2] == side]
                for i in range(num_champions):
                    if probs[i] > 0 and not analyzer.is_viable_pick(current_team_picks, idx_to_name[str(i)]):
                        probs[i] *= 0.01

            if probs.sum() == 0: break
            
            top_k = torch.topk(probs, min(options['top_n'], num_champions))
            
            if options['stochastic']:
                next_champ_idx = torch.multinomial(probs, 1).item()
            else:
                next_champ_idx = top_k.indices[0].item()
                
            champ_name = idx_to_name[str(next_champ_idx)]

            # Delta Analysis for the top pick if it's a pick
            delta_str = ""
            if act == "pick":
                delta = analyzer.compute_delta(champ_ids, action_types, sides, positions, torch.tensor([curr_team_idx]), next_champ_idx)
                delta_str = f" [Urgency Delta: {delta:.4f}]"

            color = "\033[94m" if side == "blue" else "\033[91m"
            self.stdout.write(f"Step {step+1:2}: {color}{side.upper():4}\033[0m {act.upper():4} -> {champ_name}{delta_str}")
            
            # Show other options
            for i in range(1, options['top_n']):
                idx = top_k.indices[i].item()
                val = top_k.values[i].item()
                if val > 0.01:
                    self.stdout.write(f"      - Option {i+1}: {idx_to_name[str(idx)]} ({val:.2f})")

            champ_ids[0, step] = next_champ_idx
            action_types[0, step] = 1 if act == "ban" else 2
            sides[0, step] = 1 if side == "blue" else 2
            history.append((champ_name, act, side))

            if act == "pick":
                current_team_picks = [h[0] for h in history if h[1] == "pick" and h[2] == side]
                pressure = analyzer.get_role_pressure(current_team_picks)
                p_str = ", ".join([f"{r.upper()}:{v:.1f}" for r, v in pressure.items() if v > 0])
                if p_str:
                    self.stdout.write(f"      Remaining Pressure: {p_str}")

        def v3_sorter(picks):
            picks_with_roles = []
            for i, p in enumerate(picks):
                role = analyzer.get_displayed_role(picks[:i], p)
                picks_with_roles.append((p, role))
            role_order = {"TOP": 0, "JUNGLE": 1, "MID": 2, "ADC": 3, "BOT": 3, "SUPPORT": 4, "FLEX": 5, "UNKNOWN": 6}
            picks_with_roles.sort(key=lambda x: role_order.get(x[1], 99))
            return [f"{p} ({r})" for p, r in picks_with_roles]

        self.display_summary(history, role_sorter=v3_sorter)

    def display_summary(self, history, role_sorter=None):
        self.stdout.write("\n=== Final Draft Summary ===")
        blue_picks = [h[0] for h in history if h[1] == "pick" and h[2] == "blue"]
        red_picks = [h[0] for h in history if h[1] == "pick" and h[2] == "red"]
        blue_bans = [h[0] for h in history if h[1] == "ban" and h[2] == "blue"]
        red_bans = [h[0] for h in history if h[1] == "ban" and h[2] == "red"]
        
        if role_sorter:
            blue_picks = role_sorter(blue_picks)
            red_picks = role_sorter(red_picks)

        self.stdout.write(f"BLUE Picks: {', '.join(blue_picks)}")
        self.stdout.write(f"BLUE Bans:  {', '.join(blue_bans)}")
        self.stdout.write(f"RED Picks:  {', '.join(red_picks)}")
        self.stdout.write(f"RED Bans:   {', '.join(red_bans)}\n")
