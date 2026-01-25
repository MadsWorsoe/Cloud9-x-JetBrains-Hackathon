# draft/management/commands/simulate_teams_draft.py

from django.core.management.base import BaseCommand
from draft.ml.constants import DRAFT_PHASES
from draft.models import Champion
from matches.models import Team
import torch
import torch.nn.functional as F
import numpy as np
from draft.ml.encoder import (
    encode_state, JSON_ROLE_TO_INTERNAL, ROLE_TO_IDX, 
    get_uuid_to_roles, ROLES, compute_role_pressure
)
from draft.ml.utils import find_role_assignment
from draft.ml.model import DraftPolicyNet
from draft.ml.phase import get_draft_phase
from draft.ml.analyzer import DeltaAnalyzer

# Terminal colors
RED_COLOR = "\033[91m"
BLUE_COLOR = "\033[94m"
RESET_COLOR = "\033[0m"

class Command(BaseCommand):
    help = "Simulate a full draft between two teams"

    def add_arguments(self, parser):
        parser.add_argument("team_blue", type=str)
        parser.add_argument("team_red", type=str)
        parser.add_argument("--top_n", type=int, default=3, help="Show top N options per pick/ban")
        parser.add_argument("--stochastic", action="store_true", help="Sample picks probabilistically")
        parser.add_argument("--debug", action="store_true", help="Show role pressure and state vectors")

    def handle(self, *args, **options):
        team_blue_obj = Team.objects.get(name=options["team_blue"])
        team_red_obj = Team.objects.get(name=options["team_red"])
        top_n = options["top_n"]
        stochastic = options["stochastic"]
        debug = options["debug"]

        # Load model checkpoint
        checkpoint = torch.load("draft/ml_artifacts/draft_model.pt", map_location="cpu")
        input_dim = checkpoint["input_dim"]
        num_champions = checkpoint["num_champions"]
        num_teams = checkpoint.get("num_teams", 100) # Fallback if not present
        champion_id_to_index = checkpoint["champion_id_to_index"]
        team_id_to_index = checkpoint.get("team_id_to_index", {})
        index_to_champion_id = {v: k for k, v in champion_id_to_index.items()}

        model = DraftPolicyNet(input_dim=input_dim, num_champions=num_champions, num_teams=num_teams)
        model.load_state_dict(checkpoint["model_state"])
        model.eval()

        # Map current teams to their trained indices
        # We must use external_id because drafter_id in DraftAction matches external_id
        blue_team_idx = team_id_to_index.get(team_blue_obj.external_id, 0)
        if team_blue_obj.external_id not in team_id_to_index:
            self.stdout.write(self.style.WARNING(f"Warning: Team {team_blue_obj.name} ({team_blue_obj.external_id}) not found in model's team mapping. Defaulting to index 0."))

        red_team_idx = team_id_to_index.get(team_red_obj.external_id, 0)
        if team_red_obj.external_id not in team_id_to_index:
            self.stdout.write(self.style.WARNING(f"Warning: Team {team_red_obj.name} ({team_red_obj.external_id}) not found in model's team mapping. Defaulting to index 0."))

        if debug:
            print(f"Blue team: {team_blue_obj.name} (ext_id: {team_blue_obj.external_id}) -> Index: {blue_team_idx}")
            print(f"Red team: {team_red_obj.name} (ext_id: {team_red_obj.external_id}) -> Index: {red_team_idx}")

        blue_picks = []
        red_picks = []
        blue_bans = []
        red_bans = []

        for step_num, (side, action_type) in enumerate(DRAFT_PHASES):
            team_idx = blue_team_idx if side.upper() == "BLUE" else red_team_idx
            opp_team_idx = red_team_idx if side.upper() == "BLUE" else blue_team_idx
            phase = get_draft_phase(step_num)

            side_upper = side.upper()
            if side_upper == "BLUE":
                own_picks = blue_picks
                enemy_picks = red_picks
            else:
                own_picks = red_picks
                enemy_picks = blue_picks

            # Encode state
            state = encode_state(
                own_picks=[index_to_champion_id[i] for i in own_picks],
                enemy_picks=[index_to_champion_id[i] for i in enemy_picks],
                banned_champions=[index_to_champion_id[i] for i in blue_bans + red_bans],
                side=side,
                phase=phase,
                team_idx=team_idx,
                champion_id_to_index=champion_id_to_index
            )

            x_vec = np.concatenate([
                state["own_picks"],
                state["enemy_picks"],
                state["bans"],
                state["side"],
                state["phase"],
                state["role_pressure"]
            ])
            x_tensor = torch.tensor(x_vec, dtype=torch.float32).unsqueeze(0)
            t_tensor = torch.tensor([team_idx], dtype=torch.long)
            o_tensor = torch.tensor([opp_team_idx], dtype=torch.long)

            with torch.no_grad():
                logits = model(x_tensor, t_tensor, o_tensor)
                # Use temperature to sharpen picks
                temperature = 0.5
                probs = F.softmax(logits / temperature, dim=1).squeeze(0).numpy()

            # Mask already picked/banned champions
            probs_masked = probs.copy()
            probs_masked[blue_picks + red_picks + blue_bans + red_bans] = 0
            
            # Apply role penalty if it's a pick
            if action_type.upper() == "PICK":
                mapping = get_uuid_to_roles()
                
                # Pre-calculate current team's champions' roles
                current_team_champ_roles = []
                for p_idx in own_picks:
                    uuid = index_to_champion_id[p_idx]
                    roles = mapping.get(uuid, [])
                    internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in roles]
                    current_team_champ_roles.append([r for r in internal_roles if r])

                for i in range(len(probs_masked)):
                    if probs_masked[i] == 0:
                        continue
                    
                    champ_uuid = index_to_champion_id[i]
                    champ_roles = mapping.get(champ_uuid, [])
                    if not champ_roles:
                        continue
                    
                    internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in champ_roles]
                    internal_roles = [r for r in internal_roles if r]
                    if not internal_roles:
                        continue
                    
                    # Check if adding this champion allows for a valid role assignment
                    test_roles = current_team_champ_roles + [internal_roles]
                    if not find_role_assignment(test_roles):
                        # Soft penalty: reduce probability significantly
                        probs_masked[i] *= 0.01

            # Re-normalize to make scores more meaningful
            total_prob = np.sum(probs_masked)
            if total_prob > 0:
                probs_masked /= total_prob

            # Decide pick index
            if stochastic:
                # Use the already normalized probs_masked for sampling
                pick_idx = int(np.random.choice(len(probs_masked), p=probs_masked))
            else:
                pick_idx = int(np.argmax(probs_masked))

            champion_uuid = index_to_champion_id[pick_idx]
            champion_name = Champion.objects.get(id=champion_uuid).name
            confidence = float(probs_masked[pick_idx])

            # Determine role for display if it's a pick
            role_display = ""
            if action_type.upper() == "PICK":
                mapping = get_uuid_to_roles()
                current_uuids = [index_to_champion_id[i] for i in own_picks] + [champion_uuid]
                team_roles_data = []
                for u in current_uuids:
                    r_list = mapping.get(u, [])
                    internal_r = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in r_list]
                    team_roles_data.append([r for r in internal_r if r])
                
                assignment = find_role_assignment(team_roles_data)
                if assignment:
                    role_display = f" ({assignment[-1]})"

            # Show top N options
            top_indices = probs_masked.argsort()[::-1][:top_n]
            top_champs_objs = [Champion.objects.get(id=index_to_champion_id[i]) for i in top_indices]
            top_probs = [float(probs_masked[i]) for i in top_indices]

            # Analyzer setup
            analyzer = DeltaAnalyzer(model, champion_id_to_index, index_to_champion_id)
            baseline_uuid = index_to_champion_id[int(top_indices[1])] if len(top_indices) > 1 else None

            print(f"\n--- Analysis for {side} {action_type} ---")
            for i, idx in enumerate(top_indices):
                champ_obj = top_champs_objs[i]
                prob = top_probs[i]
                
                hints = []
                if action_type.upper() == "PICK":
                    # Role pressure analysis
                    champ_uuid = index_to_champion_id[idx]
                    mapping = get_uuid_to_roles()
                    champ_roles = mapping.get(champ_uuid, [])
                    internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in champ_roles]
                    internal_roles = [r for r in internal_roles if r]
                    
                    # Current pressure
                    curr_pressure = state["role_pressure"]
                    # Pressure after this pick (simulated)
                    temp_own_picks = [index_to_champion_id[p] for p in own_picks] + [champ_uuid]
                    new_pressure = compute_role_pressure(
                        temp_own_picks, 
                        [index_to_champion_id[p] for p in enemy_picks], 
                        [index_to_champion_id[p] for p in (blue_bans + red_bans)]
                    )
                    
                    pressure_diff = curr_pressure - new_pressure
                    rel_roles = [ROLES[j] for j in range(len(ROLES)) if pressure_diff[j] > 0.05]
                    if rel_roles:
                        hints.append(f"Reduces {', '.join(rel_roles)} pressure")

                    # Flexibility
                    if len(internal_roles) > 1:
                        hints.append(f"Flex: {len(internal_roles)} roles")
                    
                    # Delta Analyzer (Derived Explanation)
                    if baseline_uuid and champ_uuid != baseline_uuid:
                        why = analyzer.analyze_pick(
                            champ_uuid, 
                            [index_to_champion_id[p] for p in own_picks], 
                            [index_to_champion_id[p] for p in enemy_picks], 
                            [index_to_champion_id[p] for p in (blue_bans + red_bans)], 
                            side, team_idx, opp_team_idx, step_num, baseline_uuid
                        )
                        if why:
                            hints.append(f"Why: {why}")

                hint_str = f" [{', '.join(hints)}]" if hints else ""
                print(f"  {i+1}. {champ_obj.name}: {prob:.2f}{hint_str}")

            # Decide pick index
            if stochastic:
                pick_idx = int(np.random.choice(len(probs_masked), p=probs_masked))
            else:
                pick_idx = int(np.argmax(probs_masked))

            champion_uuid = index_to_champion_id[pick_idx]
            champion_name = Champion.objects.get(id=champion_uuid).name
            confidence = float(probs_masked[pick_idx])

            # Determine role for display if it's a pick
            role_display = ""
            if action_type.upper() == "PICK":
                mapping = get_uuid_to_roles()
                current_uuids = [index_to_champion_id[i] for i in own_picks] + [champion_uuid]
                team_roles_data = []
                for u in current_uuids:
                    r_list = mapping.get(u, [])
                    internal_r = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in r_list]
                    team_roles_data.append([r for r in internal_r if r])
                
                assignment = find_role_assignment(team_roles_data)
                if assignment:
                    role_display = f" ({assignment[-1]})"

            # Update state
            if action_type.upper() == "PICK":
                if side_upper == "BLUE":
                    blue_picks.append(pick_idx)
                else:
                    red_picks.append(pick_idx)
            elif action_type.upper() == "BAN":
                if side_upper == "BLUE":
                    blue_bans.append(pick_idx)
                else:
                    red_bans.append(pick_idx)

            color = BLUE_COLOR if side.upper() == "BLUE" else RED_COLOR
            print(f"\n{color}DECISION: {side} {action_type}: {champion_name}{role_display} ({confidence:.2f}){RESET_COLOR}")

            if debug:
                print("Role pressure:", state["role_pressure"])
                print("Blue picks indices:", blue_picks)
                print("Red picks indices:", red_picks)
                print("Blue bans indices:", blue_bans)
                print("Red bans indices:", red_bans)
        mapping = get_uuid_to_roles()
        role_order = {role: i for i, role in enumerate(ROLES)}

        def get_sorted_picks(picks, assignment):
            # Create list of (name, role)
            picks_with_roles = []
            for idx, i in enumerate(picks):
                name = Champion.objects.get(id=index_to_champion_id[i]).name
                role = assignment[idx] if assignment else "???"
                picks_with_roles.append((name, role))
            
            # Sort by role order
            picks_with_roles.sort(key=lambda x: role_order.get(x[1], 99))
            
            return [f"{name} ({role})" for name, role in picks_with_roles]

        # For Blue
        blue_final_champs = [index_to_champion_id[i] for i in blue_picks]
        blue_final_roles_data = []
        for u in blue_final_champs:
            r_list = mapping.get(u, [])
            internal_r = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in r_list]
            blue_final_roles_data.append([r for r in internal_r if r])
        blue_assignment = find_role_assignment(blue_final_roles_data)

        # For Red
        red_final_champs = [index_to_champion_id[i] for i in red_picks]
        red_final_roles_data = []
        for u in red_final_champs:
            r_list = mapping.get(u, [])
            internal_r = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in r_list]
            red_final_roles_data.append([r for r in internal_r if r])
        red_assignment = find_role_assignment(red_final_roles_data)

        picked_names_blue = get_sorted_picks(blue_picks, blue_assignment)
        picked_names_red = get_sorted_picks(red_picks, red_assignment)

        banned_names_blue = [Champion.objects.get(id=index_to_champion_id[i]).name for i in blue_bans]
        banned_names_red = [Champion.objects.get(id=index_to_champion_id[i]).name for i in red_bans]

        print("\n=== Final Draft ===")
        print("BLUE Picks:", picked_names_blue)
        print("BLUE Bans:", banned_names_blue)
        print("RED Picks:", picked_names_red)
        print("RED Bans:", banned_names_red)
