import numpy as np
import json
from pathlib import Path

class DraftFeatureExtractor:
    def __init__(self):
        self.artifacts_dir = Path("draft/ml_artifacts")
        self.synergy_counter = self._load_json("synergy_counter.json")
        self.player_pools = self._load_json("player_pools.json")
        
    def _load_json(self, filename):
        path = self.artifacts_dir / filename
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return {}

    def get_synergy_score(self, champs):
        """champs: list of champion names/ids (strings)"""
        score = 0
        count = 0
        for i in range(len(champs)):
            for j in range(i + 1, len(champs)):
                pair = "|".join(sorted([str(champs[i]), str(champs[j])]))
                score += self.synergy_counter.get("synergy", {}).get(pair, 0)
                count += 1
        return score / max(1, count)

    def get_counter_score(self, blue_champs, red_champs):
        score = 0
        count = 0
        for bc in blue_champs:
            for rc in red_champs:
                pair = f"{bc}|{rc}"
                score += self.synergy_counter.get("counter", {}).get(pair, 0)
                count += 1
        return score / max(1, count)

    def get_player_wr(self, player_name, champ_name):
        key = f"{player_name}|{champ_name}"
        stats = self.player_pools.get(key)
        if stats:
            return (stats["wins"] + 1) / (stats["games"] + 2)
        return 0.5

    def get_feature_vector(self, blue_champs, red_champs, blue_team_id=None, red_team_id=None, blue_players=None, red_players=None):
        # 1. Synergy Scores
        b_syn = self.get_synergy_score(blue_champs)
        r_syn = self.get_synergy_score(red_champs)
        
        # 2. Counter Scores
        # Blue counter Red
        b_cnt = self.get_counter_score(blue_champs, red_champs)
        # Red counter Blue (should be inverse-ish but let's be explicit)
        r_cnt = self.get_counter_score(red_champs, blue_champs)
        
        # 3. Individual Champ WRs (average)
        avg_wr = self.synergy_counter.get("champ_avg_wr", {})
        b_avg_wr = np.mean([avg_wr.get(c, 0.5) for c in blue_champs]) if blue_champs else 0.5
        r_avg_wr = np.mean([avg_wr.get(c, 0.5) for c in red_champs]) if red_champs else 0.5
        
        # 4. Player specific WRs
        b_p_wr = 0.5
        if blue_players and blue_champs:
             wrs = []
             for p in blue_players:
                 for c in blue_champs:
                     wrs.append(self.get_player_wr(p, c))
             b_p_wr = np.mean(wrs) if wrs else 0.5
             
        r_p_wr = 0.5
        if red_players and red_champs:
             wrs = []
             for p in red_players:
                 for c in red_champs:
                     wrs.append(self.get_player_wr(p, c))
             r_p_wr = np.mean(wrs) if wrs else 0.5

        # 5. Team specific WRs (average across selected champs for the team)
        # We can use synergy_counter or similar if it has team-champ stats, 
        # but let's assume we want to include team context.
        # Since this is a simple vector, we might want to include team_id or team-specific stats.
        # For now, let's keep it as placeholders for team context if available in synergy_counter
        b_team_wr = 0.5
        r_team_wr = 0.5
        # If we had team_pools.json we could use it here.

        return np.array([
            b_syn, r_syn, b_syn - r_syn,
            b_cnt, r_cnt, b_cnt - r_cnt,
            b_avg_wr, r_avg_wr, b_avg_wr - r_avg_wr,
            b_p_wr, r_p_wr, b_p_wr - r_p_wr,
            # We could add more features here
        ])
