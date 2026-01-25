# draft/ml/analyzer.py

import torch
import torch.nn.functional as F
import numpy as np
from .encoder import encode_state, get_uuid_to_roles, ROLES
from .phase import get_draft_phase
from .constants import DRAFT_PHASES

class DeltaAnalyzer:
    def __init__(self, model, champion_id_to_index, index_to_champion_id):
        self.model = model
        self.champion_id_to_index = champion_id_to_index
        self.index_to_champion_id = index_to_champion_id

    def get_flexibility(self, picks_uuids):
        mapping = get_uuid_to_roles()
        score = 0
        for uid in picks_uuids:
            score += len(mapping.get(uid, []))
        return score

    def get_forced_roles_count(self, pressure_vec):
        # A role is "forced" if pressure is high
        return int(np.sum(pressure_vec > 0.8))

    def simulate_next_steps(self, own_picks, enemy_picks, bans, side, team_idx, opp_team_idx, total_actions, steps=2):
        curr_own = list(own_picks)
        curr_enemy = list(enemy_picks)
        curr_bans = list(bans)
        
        last_pressure = None

        for i in range(steps):
            idx = total_actions + i
            if idx >= len(DRAFT_PHASES):
                break
            
            step_side, step_action = DRAFT_PHASES[idx]
            
            # Perspective of the acting team
            if step_side.lower() == side.lower():
                acting_picks = curr_own
                opponent_picks = curr_enemy
                acting_team = team_idx
                opp_team = opp_team_idx
            else:
                acting_picks = curr_enemy
                opponent_picks = curr_own
                acting_team = opp_team_idx
                opp_team = team_idx
            
            state = encode_state(acting_picks, opponent_picks, curr_bans, step_side, get_draft_phase(idx), acting_team, self.champion_id_to_index)
            x_vec = np.concatenate([
                state["own_picks"], state["enemy_picks"], state["bans"],
                state["side"], state["phase"], state["role_pressure"]
            ])
            x_tensor = torch.tensor(x_vec, dtype=torch.float32).unsqueeze(0)
            t_tensor = torch.tensor([acting_team], dtype=torch.long)
            o_tensor = torch.tensor([opp_team], dtype=torch.long)
            
            with torch.no_grad():
                logits = self.model(x_tensor, t_tensor, o_tensor)
                probs = F.softmax(logits, dim=1).squeeze(0).numpy()
            
            mask = np.zeros_like(probs)
            taken_uuids = curr_own + curr_enemy + curr_bans
            taken_indices = [self.champion_id_to_index[u] for u in taken_uuids if u in self.champion_id_to_index]
            mask[taken_indices] = -1e9
            
            best_idx = np.argmax(probs + mask)
            best_uuid = self.index_to_champion_id[int(best_idx)]
            
            if step_action.lower() == "pick":
                if step_side.lower() == side.lower(): curr_own.append(best_uuid)
                else: curr_enemy.append(best_uuid)
            else:
                curr_bans.append(best_uuid)
            
            # Update last pressure if it's our side
            if step_side.lower() == side.lower():
                # We need pressure from OUR perspective
                # encode_state gives pressure for acting_picks. 
                # If step_side == side, then acting_picks is our team.
                # But wait, state is before the pick. We want after.
                pass

        # Final state from OUR perspective
        final_state = encode_state(curr_own, curr_enemy, curr_bans, side, get_draft_phase(min(total_actions + steps, len(DRAFT_PHASES)-1)), team_idx, self.champion_id_to_index)
        return {
            "pressure": final_state["role_pressure"],
            "picks": curr_own,
            "enemy_picks": curr_enemy,
            "bans": curr_bans
        }

    def analyze_pick(self, candidate_uuid, own_picks, enemy_picks, bans, side, team_idx, opp_team_idx, total_actions, baseline_uuid, is_ban=False):
        # Outcome if we pick candidate_uuid (simulate next 2 steps)
        res_pick = self.simulate_next_steps(own_picks + [candidate_uuid], enemy_picks, bans, side, team_idx, opp_team_idx, total_actions + 1)
        
        # Outcome if we pick baseline_uuid
        res_base = self.simulate_next_steps(own_picks + [baseline_uuid], enemy_picks, bans, side, team_idx, opp_team_idx, total_actions + 1)
            
        p_pick = res_pick["pressure"]
        p_base = res_base["pressure"]
        f_pick = self.get_flexibility(res_pick["picks"])
        f_base = self.get_flexibility(res_base["picks"])
        
        delta = {
            "role_pressure_diff": p_pick - p_base,
            "flexibility_diff": f_pick - f_base,
            "forced_roles_diff": self.get_forced_roles_count(p_pick) - self.get_forced_roles_count(p_base)
        }
        
        explanation = []
        # Logic for "Why this pick now?"
        # 1. Significant pressure reduction compared to baseline
        reduced_roles = [ROLES[i] for i in range(len(ROLES)) if delta["role_pressure_diff"][i] < -0.2]
        if reduced_roles:
            explanation.append(f"reduces {', '.join(reduced_roles)} pressure by {abs(np.min(delta['role_pressure_diff'])):.2f}")
            
        # 2. Flexibility
        if delta["flexibility_diff"] > 0:
            explanation.append("preserves future flex options")
        
        # 3. Preventing forced roles
        if delta["forced_roles_diff"] < 0:
            explanation.append("prevents forced picks later")

        # 4. Specific response
        # If the opponent's best response to baseline is very strong?
        # That's hard to measure here.

        if not explanation:
            return "strong standard ban" if is_ban else "strong standard pick"
            
        result = " + ".join(explanation)
        if len(explanation) > 1:
            return f"CRITICAL: {result}"
        return result
