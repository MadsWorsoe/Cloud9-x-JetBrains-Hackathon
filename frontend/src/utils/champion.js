export const getChampionImageUrl = (name) => {
  if (!name) return "";
  const normalized = name.replace(/[^a-zA-Z0-9]/g, "");
  return `/static/champion/${normalized}.png`;
};
