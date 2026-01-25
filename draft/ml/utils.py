from draft.ml.encoder import ROLES

def find_role_assignment(champions_roles):
    """
    champions_roles: list of lists of internal roles (e.g. [["TOP", "JUNGLE"], ["MID"]])
    Returns a list of roles (one for each champion) or None.
    """
    n = len(champions_roles)
    if n == 0:
        return []
    
    assigned = [None] * n
    used_roles = [False] * len(ROLES)
    role_to_idx = {role: i for i, role in enumerate(ROLES)}

    def backtrack(idx):
        if idx == n:
            return True
        for role in champions_roles[idx]:
            r_idx = role_to_idx.get(role)
            if r_idx is not None and not used_roles[r_idx]:
                used_roles[r_idx] = True
                assigned[idx] = role
                if backtrack(idx + 1):
                    return True
                used_roles[r_idx] = False
                assigned[idx] = None
        return False

    if backtrack(0):
        return assigned
    return None
