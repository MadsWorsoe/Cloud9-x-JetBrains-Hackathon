// src/components/Logo.jsx
import { Image } from "@chakra-ui/react";
import { getTeamLogoUrl, getTournamentLogoUrl } from "../utils/team";

export default function Logo({ name, type = "team", alt = "logo", size = "32px", mx = 1 }) {
  if (!name) return null;

  let src = "";
  if (type === "tournament") {
    src = getTournamentLogoUrl(name);
  } else {
    src = getTeamLogoUrl(name);
  }
  
  const rootLogoSrc = `/static/${name}.png`;

  return (
    <Image
      src={src}
      fallbackSrc={rootLogoSrc}
      alt={alt}
      boxSize={size}
      display="inline-block"
      verticalAlign="middle"
      mx={mx}
    />
  );
}