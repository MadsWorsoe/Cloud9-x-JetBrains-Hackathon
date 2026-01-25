import json
import os

ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]

def _load_champion_roles():
    # Path to the JSON file relative to this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "ml_artifacts", "champ_roles.json")
    
    role_map = {
        "top": "TOP",
        "jungle": "JUNGLE",
        "mid": "MID",
        "bot": "ADC",
        "support": "SUPPORT"
    }
    
    try:
        with open(json_path, "r") as f:
            raw_data = json.load(f)
        
        normalized_data = {}
        for champ, roles in raw_data.items():
            normalized_data[champ] = [role_map.get(r.lower(), r.upper()) for r in roles]
        return normalized_data
    except Exception as e:
        # Fallback or empty if file missing
        return {}

CHAMPION_ROLES = _load_champion_roles()

def compute_role_pressure(picked_champions):
    pressure = {r: 0.0 for r in ROLES}
    for champ_idx in picked_champions:
        roles = CHAMPION_ROLES.get(champ_idx, [])
        if not roles:
            continue
        w = 1.0 / len(roles)
        for r in roles:
            pressure[r] += w
    return [pressure[r] for r in ROLES]  # return list, not dict
