import { HStack, Box, Image, Text, Tooltip, VStack, Divider } from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import { getChampionImageUrl } from "../../utils/champion";
import Logo from "../Logo";
import { useMemo } from "react";
import { findRoleAssignment } from "../../utils/draft";

const flash = keyframes`
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
`;

export default function PickRow({ side, picks = [], isActing, isCompact, isComplete }) {
  const sideColor = side === "blue" ? "blue.500" : "red.500";
  const glowColor = side === "blue" ? "rgba(66, 153, 225, 0.6)" : "rgba(245, 101, 101, 0.6)";

  const boxSize = isCompact ? { base: "24px", xs: "28px", sm: "32px", md: "36px", lg: "44px" } : { base: "60px", lg: "80px" };

  return (
    <Box mb={isCompact ? 0 : 4} w={isCompact ? "48%" : "100%"}>
      {!isCompact && (
        <Text 
          fontWeight="bold" 
          textAlign={side === "blue" ? "left" : "right"}
          color={isActing ? sideColor : "inherit"}
          animation={isActing ? `${flash} 1.5s infinite ease-in-out` : "none"}
          fontSize="sm"
          mb={1}
          textTransform="capitalize"
        >
          {side} Picks
        </Text>
      )}
      <HStack spacing={isCompact ? 1 : 2} justify="space-between" align="start" w="100%">
        {Array.from({ length: 5 }).map((_, i) => {
          const champion = picks[i];
          const isCurrentSlot = isActing && picks.slice(0, i).every(b => b !== null) && champion === null;

          return (
            <Box
              key={i}
              flex="1"
              maxW={boxSize}
              border="1px solid"
              borderColor={isCurrentSlot ? sideColor : "gray.600"}
              boxShadow={isCurrentSlot ? `0 0 8px ${glowColor}` : "none"}
              borderRadius="sm"
              bg="gray.700"
              overflow="hidden"
              position="relative"
              animation={isCurrentSlot ? `${flash} 2s infinite ease-in-out` : "none"}
            >
              <Box w="100%" aspectRatio={1} overflow="hidden">
                {champion && (
                  <Tooltip
                    label={
                      isComplete && champion.stats ? (
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
                                {champion.stats.blue_side_pickrate}% ({champion.stats.blue_side_games})
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
                                {champion.stats.red_side_pickrate}% ({champion.stats.red_side_games})
                              </Text>
                            </VStack>
                          </HStack>
                        </VStack>
                      ) : null
                    }
                    isDisabled={!isComplete || !champion.stats}
                    hasArrow
                    bg="gray.800"
                    color="white"
                    borderRadius="md"
                  >
                    <Image
                      src={champion.name ? getChampionImageUrl(champion.name) : ""}
                      alt={champion.name || ""}
                      w="100%"
                      h="100%"
                      objectFit="cover"
                    />
                  </Tooltip>
                )}
              </Box>
              
              {champion && isComplete && champion.stats && (
                <Box
                  bg="gray.900"
                  px="1px"
                  py="1px"
                  borderTop="1px solid"
                  borderColor="gray.600"
                >
                  <VStack spacing={0}>
                    <Text fontSize="10px" fontWeight="black" color="white" lineHeight="1">
                      {champion.stats.winrate}%
                    </Text>
                    <Text fontSize="8px" color="gray.400" lineHeight="1">
                      {champion.stats.pickrate}%
                    </Text>
                  </VStack>
                </Box>
              )}
            </Box>
          );
        })}
      </HStack>
    </Box>
  );
}
