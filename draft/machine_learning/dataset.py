import torch
from torch.utils.data import Dataset
from draft.models import Champion, DraftAction
from matches.models import Team, Game
import json
import os

def get_champion_mapping():
    champions = Champion.objects.all().order_by('id')
    champ_to_idx = {c.id: i for i, c in enumerate(champions)}
    idx_to_champ = {i: c.id for i, c in enumerate(champions)}
    idx_to_name = {i: c.name for i, c in enumerate(champions)}
    return champ_to_idx, idx_to_champ, idx_to_name

def get_team_mapping():
    teams = Team.objects.all().order_by('id')
    team_to_idx = {t.external_id: i for i, t in enumerate(teams)}
    return team_to_idx

class DraftDataset(Dataset):
    def __init__(self, games_data, champ_to_idx, team_to_idx, num_champions):
        self.samples = []
        self.champ_to_idx = champ_to_idx
        self.num_champs = num_champions
        
        for g_data in games_data:
            actions = g_data['actions']
            team_map = g_data['team_map']
            
            for i, action in enumerate(actions):
                if i >= 20:
                    break
                    
                target_champ_idx = champ_to_idx.get(action['champion_id'])
                if target_champ_idx is None:
                    continue
                
                team_idx = team_map.get(action['team_side'].lower(), 0)
                opp_side = 'red' if action['team_side'].lower() == 'blue' else 'blue'
                opp_team_idx = team_map.get(opp_side, 0)
                
                # Store enough info to reconstruct the state
                self.samples.append({
                    "team_idx": team_idx,
                    "opp_team_idx": opp_team_idx,
                    "step": i,
                    "game_actions": [champ_to_idx.get(a['champion_id'], self.num_champs) for a in actions[:i]],
                    "game_action_types": [1 if a['action_type'] == 'ban' else 2 for a in actions[:i]],
                    "game_sides": [1 if a['team_side'].lower() == 'blue' else 2 for a in actions[:i]],
                    "target_champion": target_champ_idx
                })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        
        champ_ids = torch.full((20,), self.num_champs, dtype=torch.long)
        action_types = torch.zeros((20,), dtype=torch.long)
        sides = torch.zeros((20,), dtype=torch.long)
        positions = torch.arange(20, dtype=torch.long)
        
        i = sample['step']
        prev_champs = sample['game_actions']
        prev_types = sample['game_action_types']
        prev_sides = sample['game_sides']
        
        for j in range(i):
            champ_ids[j] = prev_champs[j]
            action_types[j] = prev_types[j]
            sides[j] = prev_sides[j]
            
        return (
            champ_ids, action_types, sides, positions, 
            torch.tensor(sample['team_idx'], dtype=torch.long), 
            torch.tensor(sample['opp_team_idx'], dtype=torch.long),
            torch.tensor(sample['target_champion'], dtype=torch.long)
        )

def prepare_data():
    from django.db.models import Prefetch
    champ_to_idx, _, _ = get_champion_mapping()
    team_to_idx = get_team_mapping()
    
    games_data = []
    # Optimize queries with select_related and prefetch_related
    draft_actions_prefetch = Prefetch(
        'draft_actions', 
        queryset=DraftAction.objects.all().order_by('sequence_number')
    )
    games = Game.objects.all().select_related('team_1', 'team_2').prefetch_related(draft_actions_prefetch)
    
    num_champs = len(champ_to_idx)
    
    for game in games:
        actions = list(game.draft_actions.all())
        if not actions:
            continue
            
        team_map = {}
        if game.team_1 and game.team_1_side:
            team_map[game.team_1_side.lower()] = team_to_idx.get(game.team_1.external_id, 0)
        if game.team_2 and game.team_2_side:
            team_map[game.team_2_side.lower()] = team_to_idx.get(game.team_2.external_id, 0)

        # Store minimal game data
        games_data.append({
            "team_map": team_map,
            "actions": [{"champion_id": a.champion_id, "action_type": a.action_type, "team_side": a.team_side} for a in actions]
        })
            
    return games_data, champ_to_idx, team_to_idx, num_champs

DRAFT_PHASES = [
    ("blue", "ban"), ("red", "ban"),
    ("blue", "ban"), ("red", "ban"),
    ("blue", "ban"), ("red", "ban"),
    ("blue", "pick"),
    ("red", "pick"), ("red", "pick"),
    ("blue", "pick"), ("blue", "pick"),
    ("red", "pick"),
    ("red", "ban"), ("blue", "ban"),
    ("red", "ban"), ("blue", "ban"),
    ("red", "pick"),
    ("blue", "pick"), ("blue", "pick"),
    ("red", "pick"),
]
