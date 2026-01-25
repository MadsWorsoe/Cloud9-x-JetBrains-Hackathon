# draft/ml/encoder.py

import numpy as np
import json
import os
from draft.models import Champion

# Roles in LoL
ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]
ROLE_TO_IDX = {role: i for i, role in enumerate(ROLES)}

# Mapping of file role names to internal role names
JSON_ROLE_TO_INTERNAL = {
    "top": "TOP",
    "jungle": "JUNGLE",
    "mid": "MID",
    "bot": "ADC",
    "support": "SUPPORT"
}

# Draft phases
PHASES = ["EARLY", "MID", "LATE"]
PHASE_TO_IDX = {p: i for i, p in enumerate(PHASES)}

SIDE_TO_IDX = {"BLUE": 0, "RED": 1}

# Load champ roles from artifact
CHAMP_ROLES = {}
try:
    # Use absolute path relative to project root if possible, or relative to this file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roles_path = os.path.join(base_dir, "ml_artifacts", "champ_roles.json")
    if os.path.exists(roles_path):
        with open(roles_path, "r") as f:
            CHAMP_ROLES = json.load(f)
except Exception as e:
    print(f"Warning: Could not load champ_roles.json: {e}")

# Global cache for UUID -> roles
UUID_TO_ROLES = None

def get_uuid_to_roles():
    global UUID_TO_ROLES
    if UUID_TO_ROLES is None:
        UUID_TO_ROLES = {}
        # We need Django to be initialized to access models
        try:
            from draft.models import Champion
            champs = Champion.objects.all()
            
            # Create a cleaned-name mapping for CHAMP_ROLES
            cleaned_champ_roles = {
                "".join(filter(str.isalnum, name)): roles 
                for name, roles in CHAMP_ROLES.items()
            }
            
            for c in champs:
                clean_name = "".join(filter(str.isalnum, c.name))
                roles = cleaned_champ_roles.get(clean_name, [])
                UUID_TO_ROLES[c.id] = roles
        except Exception as e:
            # If Django not ready yet, we'll try again later
            return {}
    return UUID_TO_ROLES

EXPECTED_POOL_SIZES = {
    "TOP": 22,
    "JUNGLE": 23,
    "MID": 25,
    "ADC": 21,
    "SUPPORT": 23
}

def compute_role_pressure(own_picks, enemy_picks=None, banned_champions=None):
    """
    Advanced role pressure vector.
    pressure(role) = 1 - (available_champions_for_role / expected_pool_size)
    If a role is already uniquely filled by own_picks, pressure is 0.
    """
    from draft.ml.utils import find_role_assignment
    
    mapping = get_uuid_to_roles()
    enemy_uuids = enemy_picks or []
    banned_uuids = banned_champions or []
    taken = set(own_picks) | set(enemy_uuids) | set(banned_uuids)
    
    # 1. Calculate available champions per role
    available_counts = np.zeros(len(ROLES), dtype=np.float32)
    for uid, roles in mapping.items():
        if uid in taken:
            continue
        for r in roles:
            internal_role = JSON_ROLE_TO_INTERNAL.get(r.lower())
            if internal_role in ROLE_TO_IDX:
                available_counts[ROLE_TO_IDX[internal_role]] += 1
                
    # 2. Determine which roles are still needed
    own_roles_data = []
    for uid in own_picks:
        roles = mapping.get(uid, [])
        internal_roles = [JSON_ROLE_TO_INTERNAL.get(r.lower()) for r in roles]
        own_roles_data.append([r for r in internal_roles if r])

    needed_mask = np.zeros(len(ROLES), dtype=np.float32)
    for i, role in enumerate(ROLES):
        # Can we assign current picks to roles OTHER than 'role'?
        other_roles = [r for r in ROLES if r != role]
        
        filtered_data = []
        for cr in own_roles_data:
            filtered_data.append([r for r in cr if r in other_roles])
        
        if find_role_assignment(filtered_data) is not None:
            needed_mask[i] = 1.0
        else:
            needed_mask[i] = 0.0
            
    expected = np.array([EXPECTED_POOL_SIZES[r] for r in ROLES], dtype=np.float32)
    raw_pressure = 1.0 - (available_counts / expected)
    raw_pressure = np.clip(raw_pressure, 0, 1.0)
    
    return raw_pressure * needed_mask


def encode_state(own_picks, enemy_picks, banned_champions, side, phase, team_idx=0, champion_id_to_index=None):
    """
    Encode the current draft state for model input.
    """
    if champion_id_to_index is None:
        all_champions = Champion.objects.all()
        champ_ids = [c.id for c in all_champions]
        champion_id_to_index = {cid: i for i, cid in enumerate(champ_ids)}

    index_to_id = {v: k for k, v in champion_id_to_index.items()}
    num_champs = len(champion_id_to_index)

    def to_uuids(items):
        res = []
        for c in items:
            if isinstance(c, (int, np.integer)):
                if int(c) in index_to_id:
                    res.append(index_to_id[int(c)])
            else:
                res.append(c)
        return res

    own_uuids = to_uuids(own_picks)
    enemy_uuids = to_uuids(enemy_picks)
    banned_uuids = to_uuids(banned_champions)

    own_picks_vec = np.zeros(num_champs, dtype=np.float32)
    for c in own_picks:
        if c in champion_id_to_index:
            own_picks_vec[champion_id_to_index[c]] = 1.0
        elif isinstance(c, (int, np.integer)) and 0 <= c < num_champs:
            own_picks_vec[int(c)] = 1.0

    enemy_picks_vec = np.zeros(num_champs, dtype=np.float32)
    for c in enemy_picks:
        if c in champion_id_to_index:
            enemy_picks_vec[champion_id_to_index[c]] = 1.0
        elif isinstance(c, (int, np.integer)) and 0 <= c < num_champs:
            enemy_picks_vec[int(c)] = 1.0

    bans_vec = np.zeros(num_champs, dtype=np.float32)
    for c in banned_champions:
        if c in champion_id_to_index:
            bans_vec[champion_id_to_index[c]] = 1.0
        elif isinstance(c, (int, np.integer)) and 0 <= c < num_champs:
            bans_vec[int(c)] = 1.0

    # Side one-hot
    side_vec = np.zeros(len(SIDE_TO_IDX), dtype=np.float32)
    side_upper = side.upper()
    if side_upper in SIDE_TO_IDX:
        side_vec[SIDE_TO_IDX[side_upper]] = 1.0

    # Phase one-hot
    phase_vec = np.zeros(len(PHASES), dtype=np.float32)
    phase_upper = phase.upper()
    if phase_upper in PHASE_TO_IDX:
        phase_vec[PHASE_TO_IDX[phase_upper]] = 1.0

    role_pressure_vec = compute_role_pressure(own_uuids, enemy_uuids, banned_uuids)

    return {
        "own_picks": own_picks_vec,
        "enemy_picks": enemy_picks_vec,
        "bans": bans_vec,
        "side": side_vec,
        "phase": phase_vec,
        "role_pressure": role_pressure_vec,
        "team_idx": team_idx
    }
