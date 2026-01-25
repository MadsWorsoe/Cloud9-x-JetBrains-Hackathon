import torch
import json
import os
import numpy as np

ROLES = ["top", "jungle", "mid", "bot", "support"]
REQUIRED_SLOTS = {role: 1.0 for role in ROLES}

class DeltaAnalyzerV2:
    def __init__(self, model, champ_to_idx, idx_to_champ, idx_to_name, champ_roles_path):
        self.model = model
        self.champ_to_idx = champ_to_idx
        self.idx_to_champ = idx_to_champ
        self.idx_to_name = idx_to_name
        self.champ_roles = {}
        if os.path.exists(champ_roles_path):
            with open(champ_roles_path, 'r') as f:
                data = json.load(f)
                self.champ_roles = {self.normalize_name(k): v for k, v in data.items()}
        
        # Load synergies if available
        self.synergies = {}
        self.counters = {}
        synergy_path = os.path.join(os.path.dirname(champ_roles_path), "synergy_counter.json")
        if os.path.exists(synergy_path):
            try:
                with open(synergy_path, 'r') as f:
                    data = json.load(f)
                    self.synergies = data.get("synergy", {})
                    self.counters = data.get("counter", {})
            except:
                pass

    def normalize_name(self, name):
        if not name: return ""
        return name.replace("'", "").replace(" ", "").replace(".", "").lower()

    def get_synergy_score(self, champ1, champ2):
        key = f"{champ1}|{champ2}"
        key_rev = f"{champ2}|{champ1}"
        return self.synergies.get(key, 0) or self.synergies.get(key_rev, 0)

    def get_counter_score(self, counter_champ, target_champ):
        key = f"{counter_champ}|{target_champ}"
        return self.counters.get(key, 0)

    def role_coverage(self, picks):
        """
        picks: list of champion names
        """
        coverage = {role: 0.0 for role in ROLES}
        for champ_name in picks:
            roles = self.champ_roles.get(self.normalize_name(champ_name), [])
            if not roles:
                continue
            for r in roles:
                if r.lower() in coverage:
                    coverage[r.lower()] += 1 / len(roles)
        return coverage

    def get_role_pressure(self, picks):
        coverage = self.role_coverage(picks)
        pressure = {role: max(0, REQUIRED_SLOTS[role] - coverage[role]) for role in ROLES}
        return pressure

    def compute_delta(self, champ_ids, action_types, sides, positions, team_idx, opp_team_idx, candidate_champ_idx, opp_side_val=None):
        self.model.eval()
        
        # Ensure indices are tensors
        if not isinstance(team_idx, torch.Tensor):
            team_idx = torch.tensor([team_idx], device=champ_ids.device)
        if not isinstance(opp_team_idx, torch.Tensor):
            opp_team_idx = torch.tensor([opp_team_idx], device=champ_ids.device)

        with torch.no_grad():
            # Step 1: current distribution
            logits_now = self.model(champ_ids, action_types, sides, positions, team_idx, opp_team_idx)
            p_now = torch.softmax(logits_now, dim=-1)

            # Step 2: simulate skipping a candidate (opponent takes it)
            # When we skip, the opponent picks it.
            # In their perspective, they are the acting team and WE are the opponent.
            new_champ_ids = champ_ids.clone()
            new_action_types = action_types.clone()
            new_sides = sides.clone()
            
            num_champs = self.model.num_champions
            # Find the first PAD slot
            is_pad = (new_champ_ids == num_champs)
            if not is_pad.any():
                return 0.0
            
            first_pad = is_pad.nonzero(as_tuple=True)[1][0].item()
            
            # Use provided opponent side or infer it
            if opp_side_val is not None:
                opp_side = opp_side_val
            else:
                last_side = 1
                if first_pad > 0:
                    last_side = sides[0, first_pad-1].item()
                opp_side = 2 if last_side == 1 else 1
            
            new_champ_ids[0, first_pad] = candidate_champ_idx
            new_action_types[0, first_pad] = 2 # PICK
            new_sides[0, first_pad] = opp_side
            
            # Important: when simulating the AFTER state, the model should see it from our perspective.
            # But the opponent just took a champion.
            logits_after = self.model(new_champ_ids, new_action_types, new_sides, positions, team_idx, opp_team_idx)
            p_after = torch.softmax(logits_after, dim=-1)
            
            # Step 3: KL divergence
            delta = torch.sum(p_now * (torch.log(p_now + 1e-9) - torch.log(p_after + 1e-9))).item()
            return delta

    def get_displayed_role(self, picks_so_far, new_pick_name):
        """
        Assign new_pick_name to the role with highest current pressure.
        """
        pressure = self.get_role_pressure(picks_so_far)
        roles = self.champ_roles.get(self.normalize_name(new_pick_name), [])
        if not roles:
            return "UNKNOWN"
        
        roles = [r.lower() for r in roles if r.lower() in ROLES]
        if not roles:
            return "FLEX"
            
        best_role = roles[0]
        max_p = -1
        is_flex = False
        
        for r in roles:
            if pressure[r] > max_p:
                max_p = pressure[r]
                best_role = r
                is_flex = False
            elif pressure[r] == max_p:
                is_flex = True
                
        return "FLEX" if is_flex else best_role.upper()

    def find_role_assignment(self, champions_roles):
        """
        champions_roles: list of lists of roles (e.g. [["top", "jungle"], ["mid"]])
        """
        n = len(champions_roles)
        if n == 0:
            return []
        
        assigned = [None] * n
        used_roles = {role: False for role in ROLES}

        def backtrack(idx):
            if idx == n:
                return True
            for role in champions_roles[idx]:
                if role in used_roles and not used_roles[role]:
                    used_roles[role] = True
                    assigned[idx] = role
                    if backtrack(idx + 1):
                        return True
                    used_roles[role] = False
                    assigned[idx] = None
            return False

        if backtrack(0):
            return assigned
        return None

    def is_viable_pick(self, current_picks, new_pick_name):
        """
        Check if adding new_pick_name to current_picks allows for a valid role assignment.
        current_picks: list of champion names
        """
        all_picks = current_picks + [new_pick_name]
        if len(all_picks) > 5:
            return False
            
        champions_roles = []
        for name in all_picks:
            roles = self.champ_roles.get(self.normalize_name(name), [])
            roles = [r.lower() for r in roles if r.lower() in ROLES]
            if not roles:
                # If we don't know the roles, we assume it's a flex
                roles = ROLES
            champions_roles.append(roles)
            
        return self.find_role_assignment(champions_roles) is not None

    def analyze_pick(self, candidate_name, own_picks_names, enemy_picks_names, all_bans_names, side, team_idx, opp_team_idx, total_actions, baseline_name, champ_ids, action_types, sides, positions, opp_side_val=None, candidate_idx=None, is_ban=False):
        """
        Provides a descriptive explanation for a pick.
        """
        explanation = []
        
        # 1. Synergy Analysis
        best_synergy = 0
        best_ally = ""
        # If it's a ban, we look at synergy with ENEMY team (to deny it)
        synergy_targets = enemy_picks_names if is_ban else own_picks_names
        for target in synergy_targets:
            score = self.get_synergy_score(candidate_name, target)
            if score > best_synergy:
                best_synergy = score
                best_ally = target
        
        if best_synergy > 0.05:
            if is_ban:
                explanation.append(f"Denies synergy with {best_ally}")
            else:
                explanation.append(f"Strong synergy with {best_ally}")

        # 2. Counter Analysis
        best_counter = 0
        best_target = ""
        # If it's a pick, we counter the enemy. 
        # If it's a ban, we prevent the enemy from countering us.
        counter_targets = own_picks_names if is_ban else enemy_picks_names
        for target in counter_targets:
            # If is_ban, we want to see if candidate counters our team
            if is_ban:
                score = self.get_counter_score(candidate_name, target)
            else:
                score = self.get_counter_score(candidate_name, target)
            
            if score > best_counter:
                best_counter = score
                best_target = target
        
        if best_counter > 0.05:
            if is_ban:
                explanation.append(f"Prevents counter against {best_target}")
            else:
                explanation.append(f"Counter-pick against {best_target}")

        # 3. Role pressure analysis
        roles = self.champ_roles.get(self.normalize_name(candidate_name), [])
        is_flex = len(roles) > 1

        if not is_ban and not is_flex:
            curr_pressure = self.get_role_pressure(own_picks_names)
            new_pressure = self.get_role_pressure(own_picks_names + [candidate_name])
            
            pressure_diff = {r: curr_pressure[r] - new_pressure[r] for r in ROLES}
            rel_roles = [r.upper() for r in ROLES if pressure_diff[r] > 0.3] 
            
            if rel_roles:
                explanation.append(f"{rel_roles[0]} role")

        # 4. Flexibility
        if is_flex:
            explanation.append(f"Flexible pick ({len(roles)} roles)")

        # 5. Urgency (Delta)
        if candidate_idx is not None:
             delta = self.compute_delta(champ_ids, action_types, sides, positions, team_idx, opp_team_idx, candidate_idx, opp_side_val)
             if delta > 0.15:
                 explanation.append("Urgent: Highly contested")
             elif delta > 0.05:
                 explanation.append("Contested pick")

        # 6. Pick Order Timing
        if total_actions < 10: # Phase 1
             if is_flex and len(explanation) < 3:
                 explanation.append("Flexible early pick")
        else: # Phase 2
             if best_counter > 0.03:
                 explanation.append("Strategic late-game counter")

        # Return combined explanation
        if not explanation:
            return "Solid tactical ban" if is_ban else "Solid tactical pick"
        
        result = " + ".join(explanation[:2])
        if len(explanation) > 1:
            return f"CRITICAL: {result}"
        return result

    def get_team_intent(self, champ_ids, action_types, sides, positions, acting_team_idx, opponent_team_idx, picks_names=None):
        """
        Predicts a team's most likely next moves, accounting for missing roles.
        """
        # Ensure indices are tensors
        if not isinstance(acting_team_idx, torch.Tensor):
            acting_team_idx = torch.tensor([acting_team_idx], device=champ_ids.device)
        if not isinstance(opponent_team_idx, torch.Tensor):
            opponent_team_idx = torch.tensor([opponent_team_idx], device=champ_ids.device)

        self.model.eval()
        with torch.no_grad():
            logits = self.model(champ_ids, action_types, sides, positions, acting_team_idx, opponent_team_idx)
            probs = torch.softmax(logits, dim=-1)[0]
        
        num_champions = self.model.num_champions
        mask = torch.ones_like(probs)
        for i in range(champ_ids.size(1)):
            val = champ_ids[0, i].item()
            if val < num_champions:
                mask[val] = 0
        
        # Filter by role viability if picks are provided
        if picks_names is not None:
            pressure = self.get_role_pressure(picks_names)
            missing_roles = [r for r, v in pressure.items() if v > 0.1]
            
            if missing_roles and len(picks_names) < 5:
                role_mask = torch.zeros_like(probs)
                for idx_str, name in self.idx_to_name.items():
                    idx = int(idx_str)
                    if idx >= num_champions: continue
                    
                    champ_roles = [r.lower() for r in self.champ_roles.get(self.normalize_name(name), [])]
                    # If champion can fill any of the missing roles, it's a candidate
                    if any(r in missing_roles for r in champ_roles):
                        role_mask[idx] = 1.0
                
                # Apply role mask if it's not empty (don't want to mask everything if no champ fits)
                if role_mask.sum() > 0:
                    mask = mask * role_mask

        probs = probs * mask
        
        k = min(5, probs.size(0))
        top_k = torch.topk(probs, k)
        return [{"name": self.idx_to_name[str(idx.item())], "prob": prob.item()} for idx, prob in zip(top_k.indices, top_k.values) if prob.item() > 0.01]

    def get_general_insights(self, champ_ids, action_types, sides, positions, team_idx, opp_team_idx, own_picks_names, enemy_picks_names, all_bans_names, total_actions, side, action_type):
        # Ensure indices are tensors
        if not isinstance(team_idx, torch.Tensor):
            team_idx = torch.tensor([team_idx], device=champ_ids.device)
        if not isinstance(opp_team_idx, torch.Tensor):
            opp_team_idx = torch.tensor([opp_team_idx], device=champ_ids.device)

        self.model.eval()
        with torch.no_grad():
            logits = self.model(champ_ids, action_types, sides, positions, team_idx, opp_team_idx)
            probs = torch.softmax(logits, dim=-1)[0]
            
            # Mask already used champions
            num_champions = self.model.num_champions
            mask = torch.ones_like(probs)
            for i in range(champ_ids.size(1)):
                val = champ_ids[0, i].item()
                if val < num_champions:
                    mask[val] = 0
            probs = probs * mask
            
        # Urgency: Check if delta of top pick is high
        top_champ_idx = torch.argmax(probs).item()
        top_champ_name = self.idx_to_name[str(top_champ_idx)]
        opp_side_val = 2 if side == 'blue' else 1
        delta = self.compute_delta(champ_ids, action_types, sides, positions, team_idx, opp_team_idx, top_champ_idx, opp_side_val)
        
        urgent_champ = None
        if delta > 0.15:
            urgency = "Urgent: Pick or lose"
            urgent_champ = top_champ_name
        elif delta > 0.05:
            urgency = "Contested"
        else:
            urgency = "Can wait"

        # Team Intent (Both sides)
        # Identify who is Blue and who is Red in terms of indices
        # If side == 'blue', then team_idx is Blue, opp_team_idx is Red
        if side == 'blue':
            blue_idx, red_idx = team_idx, opp_team_idx
            blue_picks, red_picks = own_picks_names, enemy_picks_names
        else:
            blue_idx, red_idx = opp_team_idx, team_idx
            blue_picks, red_picks = enemy_picks_names, own_picks_names

        blue_intent = self.get_team_intent(champ_ids, action_types, sides, positions, blue_idx, red_idx, picks_names=blue_picks)
        red_intent = self.get_team_intent(champ_ids, action_types, sides, positions, red_idx, blue_idx, picks_names=red_picks)

        # Missing Roles
        blue_pressure = self.get_role_pressure(blue_picks)
        red_pressure = self.get_role_pressure(red_picks)
        blue_missing = [r.upper() for r, v in blue_pressure.items() if v > 0.8]
        red_missing = [r.upper() for r, v in red_pressure.items() if v > 0.8]
        
        # Being forced?
        forced = "Yes" if delta > 0.2 else "No"
        
        return {
            "urgency": urgency,
            "urgent_champ": urgent_champ,
            "missing_roles": {
                "blue": blue_missing,
                "red": red_missing
            },
            "team_intent": {
                "blue": blue_intent,
                "red": red_intent
            },
            "forced": forced,
        }

    def index_to_name_reverse(self, name):
        # find the champion ID for this name
        from draft.models import Champion
        try:
            return Champion.objects.get(name=name).id
        except:
            return None
