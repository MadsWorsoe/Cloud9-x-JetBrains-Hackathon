import numpy as np
import joblib
from pathlib import Path
from draft.models import Champion, Team

class DraftModelEncoder:
    def __init__(self):
        self.champ_map = {}
        self.team_map = {}
        self.num_champions = 0
        self.num_teams = 0

    def fit(self):
        """Builds the ID -> Integer mapping from the database."""
        # We start at 1 because 0 is reserved for padding (empty pick)
        self.champ_map = {str(c.id): i + 1 for i, c in enumerate(Champion.objects.all().order_by('id'))}
        self.team_map = {str(t.id): i + 1 for i, t in enumerate(Team.objects.all().order_by('id'))}
        
        self.num_champions = len(self.champ_map) + 1
        self.num_teams = len(self.team_map) + 1
        return self

    def save(self, path):
        joblib.dump({
            "champ_map": self.champ_map,
            "team_map": self.team_map,
            "num_champs": self.num_champions,
            "num_teams": self.num_teams
        }, path)

    def load(self, path):
        data = joblib.load(path)
        self.champ_map = data["champ_map"]
        self.team_map = data["team_map"]
        self.num_champions = data["num_champs"]
        self.num_teams = data["num_teams"]
        return self

    def get_team_id(self, db_id):
        return self.team_map.get(str(db_id), 0) # 0 if unknown team

    def get_champ_ids(self, db_ids):
        # Always return list of length 5
        ids = [self.champ_map.get(str(x), 0) for x in db_ids if x]
        return ids + [0] * (5 - len(ids))
