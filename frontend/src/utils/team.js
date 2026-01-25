export const getTeamLogoUrl = (name) => {
  if (!name) return "";
  return `/static/logos/teams/${name}.png`;
};

export const getTournamentLogoUrl = (name) => {
  if (!name) return "";
  // Normalization for tournaments: lowercase and remove non-alphanumeric
  // We also handle cases like "LCK - Split 2" by taking the first word for common prefixes
  const normalized = name.toLowerCase().replace(/[^a-z0-9]/g, "");
  
  // Special cases for common tournament prefixes
  if (normalized.startsWith("lck")) return "/static/logos/tournaments/lck.png";
  if (normalized.startsWith("lec")) return "/static/logos/tournaments/lec.png";
  if (normalized.startsWith("lpl")) return "/static/logos/tournaments/lpl.png";
  if (normalized.startsWith("lcp")) return "/static/logos/tournaments/lcp.png";
  if (normalized.startsWith("worlds")) return "/static/logos/tournaments/worlds.png";
  if (normalized.startsWith("msi")) return "/static/logos/tournaments/msi.png";
  if (normalized.startsWith("lta")) {
    if (normalized.includes("north")) return "/static/logos/tournaments/ltanorth.png";
    if (normalized.includes("south")) return "/static/logos/tournaments/ltasouth.png";
    return "/static/logos/tournaments/lta.png";
  }
  
  return `/static/logos/tournaments/${normalized}.png`;
};

export const getRoleLogoUrl = (role) => {
  if (!role) return "";
  return `/static/logos/roles/${role.toLowerCase()}.png`;
};
