/**
 * Utility for draft-related logic, specifically role assignment.
 */

const ROLE_MAPPING = {
  "top": "Top",
  "jungle": "Jungle",
  "mid": "Mid",
  "bot": "ADC",
  "support": "Support"
};

const ORDERED_ROLES = ["Top", "Jungle", "Mid", "ADC", "Support"];

/**
 * Finds an optimal assignment of roles for a list of 5 champions.
 * @param {Array} picks - Array of 5 champion objects, each with a 'roles' array.
 * @returns {Array} - Array of 5 roles (strings) corresponding to each champion index.
 */
export function findRoleAssignment(picks) {
  if (!picks || picks.length !== 5 || picks.some(p => !p)) {
    return picks.map((_, i) => ORDERED_ROLES[i]); // Fallback to default
  }

  // Map each champion's roles to our internal names
  const championPossibleRoles = picks.map(p => 
    (p.roles || []).map(r => ROLE_MAPPING[r.toLowerCase()] || r)
  );

  const n = picks.length;
  const assigned = new Array(n).fill(null);
  const usedRoles = new Set();

  function backtrack(idx) {
    if (idx === n) {
      return true;
    }

    const possible = championPossibleRoles[idx];
    // If champion has no roles listed, we'll try all roles as fallback
    const rolesToTry = possible.length > 0 ? possible : ORDERED_ROLES;

    for (const role of rolesToTry) {
      if (!usedRoles.has(role)) {
        usedRoles.add(role);
        assigned[idx] = role;
        if (backtrack(idx + 1)) {
          return true;
        }
        usedRoles.delete(role);
        assigned[idx] = null;
      }
    }
    return false;
  }

  if (backtrack(0)) {
    return assigned;
  }

  // Fallback: Greedy assignment if perfect assignment not found
  const greedyAssigned = new Array(n).fill(null);
  const used = new Set();
  
  // 1. Assign champions to their primary (first) role if available
  picks.forEach((p, i) => {
    const possible = championPossibleRoles[i];
    if (possible.length > 0) {
      for (const role of possible) {
        if (!used.has(role)) {
          greedyAssigned[i] = role;
          used.add(role);
          break;
        }
      }
    }
  });

  // 2. Fill remaining slots with available roles from ORDERED_ROLES
  picks.forEach((p, i) => {
    if (!greedyAssigned[i]) {
      for (const role of ORDERED_ROLES) {
        if (!used.has(role)) {
          greedyAssigned[i] = role;
          used.add(role);
          break;
        }
      }
    }
  });

  // 3. Absolute fallback if somehow still missing (shouldn't happen with 5 slots/5 roles)
  return greedyAssigned.map((r, i) => r || ORDERED_ROLES[i]);
}
