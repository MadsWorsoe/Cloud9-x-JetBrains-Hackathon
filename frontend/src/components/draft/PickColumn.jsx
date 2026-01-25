import { VStack, Box, Text, Image, HStack, Tooltip, Divider } from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import { getChampionImageUrl } from "../../utils/champion";
import Logo from "../Logo";
import { useMemo } from "react";
import { findRoleAssignment } from "../../utils/draft";

const flash = keyframes`
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
`;

export default function PickColumn({ side, picks = [], isActing, isComplete }) {
  const isBlue = side.toLowerCase() === "blue";
  const sideColor = isBlue ? "blue.500" : "red.500";
  const glowColor = isBlue ? "rgba(66, 153, 225, 0.6)" : "rgba(245, 101, 101, 0.6)";

  return (
    <VStack spacing={2} align="stretch">
      <Text 
        fontWeight="bold" 
        textAlign={isBlue ? "left" : "right"}
        color={isActing ? sideColor : "inherit"}
        animation={isActing ? `${flash} 1.5s infinite ease-in-out` : "none"}
        fontSize="sm"
      >
        {side} Picks
      </Text>

      {Array.from({ length: 5 }).map((_, i) => {
        const champion = picks[i];
        const isCurrentSlot = isActing && picks.slice(0, i).every(p => p !== null) && champion === null;

        return (
          <Tooltip
            key={i}
            label={
              isComplete && champion?.stats ? (
                <VStack align="start" spacing={1} p={1}>
                  <Text fontWeight="bold" fontSize="xs">Pick Stats for {champion.name}</Text>
                  <Divider />
                  <HStack justify="space-between" w="100%">
                    <Text fontSize="2xs">Blue Side:</Text>
                    <VStack align="end" spacing={0}>
                      <Text fontSize="2xs" fontWeight="bold">
                        {champion.stats.blue_side_winrate}% WR
                      </Text>
                      <Text fontSize="2xs" color="gray.400">
                         {champion.stats.blue_side_games} Games ({champion.stats.blue_side_pickrate}%)
                      </Text>
                    </VStack>
                  </HStack>
                  <HStack justify="space-between" w="100%">
                    <Text fontSize="2xs">Red Side:</Text>
                    <VStack align="end" spacing={0}>
                      <Text fontSize="2xs" fontWeight="bold">
                        {champion.stats.red_side_winrate}% WR
                      </Text>
                      <Text fontSize="2xs" color="gray.400">
                         {champion.stats.red_side_games} Games ({champion.stats.red_side_pickrate}%)
                      </Text>
                    </VStack>
                  </HStack>
                </VStack>
              ) : null
            }
            isDisabled={!isComplete || !champion?.stats}
            hasArrow
            bg="gray.800"
            color="white"
            borderRadius="md"
          >
            <Box
              w="100%"
              h="80px"
              border="1px solid"
              borderColor={isCurrentSlot ? sideColor : "gray.600"}
              boxShadow={isCurrentSlot ? `0 0 10px ${glowColor}` : "none"}
              borderRadius="md"
              bg="gray.800"
              overflow="hidden"
              display="flex"
              alignItems="center"
              px={2}
              animation={isCurrentSlot ? `${flash} 2s infinite ease-in-out` : "none"}
            >
              {champion ? (
                <HStack spacing={3} w="100%">
                  {champion.name && (
                    <Image
                      src={getChampionImageUrl(champion.name)}
                      alt={champion.name}
                      h="64px"
                      w="64px"
                      borderRadius="sm"
                    />
                  )}
                  <VStack align="start" spacing={0} flex={1}>
                    <Text fontWeight="medium">{champion.name}</Text>
                    {isComplete && champion.stats && (
                      <VStack align="start" spacing={0}>
                        <Text fontSize="xs" fontWeight="bold" color={champion.stats.winrate >= 50 ? "green.400" : "red.400"}>
                          {champion.stats.winrate}% WR
                        </Text>
                        <Text fontSize="xs" color="gray.400">
                          {champion.stats.games_played} Games ({champion.stats.pickrate}%)
                        </Text>
                      </VStack>
                    )}
                  </VStack>
                </HStack>
              ) : (
                <Text color="gray.500" fontSize="sm">
                  {isCurrentSlot ? `Picking...` : "Empty"}
                </Text>
              )}
            </Box>
          </Tooltip>
        );
      })}
    </VStack>
  );
}
