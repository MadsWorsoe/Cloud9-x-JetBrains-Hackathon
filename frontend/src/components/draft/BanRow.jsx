import { HStack, Box, Image, Text, Tooltip, VStack, Divider } from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import { getChampionImageUrl } from "../../utils/champion";

const flash = keyframes`
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
`;

export default function BanRow({ side, bans = [], isActing, isCompact, isComplete, opponentName, teamName }) {
  const sideColor = side === "blue" ? "blue.500" : "red.500";
  const glowColor = side === "blue" ? "rgba(66, 153, 225, 0.6)" : "rgba(245, 101, 101, 0.6)";

  const boxSize = isCompact ? "40px" : "55px";

  return (
    <Box mb={isCompact ? 0 : 4}>
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
          {side} Bans
        </Text>
      )}
      <HStack spacing={isCompact ? 1 : 2} justify={side === "blue" ? "flex-start" : "flex-end"}>
        {Array.from({ length: 5 }).map((_, i) => {
          const champion = bans[i];
          const isCurrentSlot = isActing && bans.slice(0, i).every(b => b !== null) && champion === null;

          return (
            <Box
              key={i}
              w={boxSize}
              h={boxSize}
              border="1px solid"
              borderColor={isCurrentSlot ? sideColor : "gray.600"}
              boxShadow={isCurrentSlot ? `0 0 8px ${glowColor}` : "none"}
              borderRadius="sm"
              bg="gray.700"
              overflow="hidden"
              position="relative"
              animation={isCurrentSlot ? `${flash} 2s infinite ease-in-out` : "none"}
            >
              {champion && (
                <Tooltip
                  label={
                    isComplete && champion.stats ? (
                      <VStack align="start" spacing={1} p={1}>
                        <Text fontWeight="bold" fontSize="xs">Ban Stats for {champion.name}</Text>
                        <Divider />
                        <Text fontSize="2xs" fontWeight="bold">
                          {opponentName ? `Banrate against ${opponentName}` : "Banned by opponent"}:
                        </Text>
                        <HStack justify="space-between" w="100%">
                          <Text fontSize="2xs">Total:</Text>
                          <Text fontSize="2xs" fontWeight="bold">{champion.stats.opponent_banrate}% ({champion.stats.total_opponent_bans})</Text>
                        </HStack>
                        <HStack justify="space-between" w="100%">
                          <Text fontSize="2xs">Blue Side:</Text>
                          <Text fontSize="2xs">{champion.stats.blue_side_opponent_banrate}% ({champion.stats.blue_side_opponent_bans})</Text>
                        </HStack>
                        <HStack justify="space-between" w="100%">
                          <Text fontSize="2xs">Red Side:</Text>
                          <Text fontSize="2xs">{champion.stats.red_side_opponent_banrate}% ({champion.stats.red_side_opponent_bans})</Text>
                        </HStack>
                        <Divider />
                        <Text fontSize="2xs" fontWeight="bold">
                          {teamName ? `Banned by ${teamName}` : "Self-bans"}:
                        </Text>
                        <HStack justify="space-between" w="100%">
                          <Text fontSize="2xs">Total:</Text>
                          <Text fontSize="2xs" fontWeight="bold">{champion.stats.self_banrate}% ({champion.stats.total_self_bans})</Text>
                        </HStack>
                        <HStack justify="space-between" w="100%">
                          <Text fontSize="2xs">Blue Side:</Text>
                          <Text fontSize="2xs">{champion.stats.blue_side_self_banrate}% ({champion.stats.blue_side_self_bans})</Text>
                        </HStack>
                        <HStack justify="space-between" w="100%">
                          <Text fontSize="2xs">Red Side:</Text>
                          <Text fontSize="2xs">{champion.stats.red_side_self_banrate}% ({champion.stats.red_side_self_bans})</Text>
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
                  <Box position="relative" w="100%" h="100%">
                    <Image
                      src={champion.name ? getChampionImageUrl(champion.name) : ""}
                      alt={champion.name || ""}
                      filter="grayscale(100%)"
                      opacity={0.7}
                    />
                    {isComplete && champion.stats && (
                      <Box
                        position="absolute"
                        bottom="0"
                        left="0"
                        right="0"
                        bg="rgba(0,0,0,0.8)"
                        px="1px"
                        py="1px"
                      >
                        <Text fontSize="9px" fontWeight="black" color="white" textAlign="center" lineHeight="1">
                          {champion.stats.opponent_banrate}%
                        </Text>
                      </Box>
                    )}
                  </Box>
                </Tooltip>
              )}
            </Box>
          );
        })}
      </HStack>
    </Box>
  );
}
