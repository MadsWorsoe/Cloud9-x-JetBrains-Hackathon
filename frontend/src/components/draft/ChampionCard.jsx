import { Box, Image, Tooltip, Badge, VStack, Text } from "@chakra-ui/react"
import { getChampionImageUrl } from "../../utils/champion"
import { useMemo } from "react"

export function ChampionCard({ champion, onClick, isLocked, isComplete, isSelecting, score, hints, isFeatured }) {
  const filter = isLocked ? "grayscale(100%)" : (isComplete ? "grayscale(90%)" : "none");
  const opacity = isLocked ? 0.4 : (isComplete ? 0.7 : 1);
  const isDisabled = isLocked || isComplete || isSelecting;

  const tooltipLabel = useMemo(() => {
    if (!score && !hints) return champion.name;
    
    return (
      <VStack align="start" spacing={0} p={1}>
        <Text fontWeight="bold">{champion.name} {score !== undefined && `(${(score * 100).toFixed(1)}%)`}</Text>
        {hints?.pressure_reduction && (
          <Text fontSize="xs">Reduces pressure: {hints.pressure_reduction.join(", ")}</Text>
        )}
        {hints?.flex_roles && (
          <Text fontSize="xs">Flex: {hints.flex_roles.join("/")}</Text>
        )}
        {hints?.opponent_response && (
          <Text fontSize="xs" color="orange.200">Counter: {hints.opponent_response.champion_name}</Text>
        )}
        {hints?.why && (
          <Text fontSize="xs" color="blue.200" mt={1}>Insight: {hints.why}</Text>
        )}
      </VStack>
    );
  }, [champion.name, score, hints]);

  const cardContent = (
    <Box
      cursor={isDisabled ? "not-allowed" : "pointer"}
      borderRadius="md"
      overflow="hidden"
      _hover={!isDisabled ? { transform: "scale(1.05)" } : {}}
      transition="transform 0.1s"
      onClick={!isDisabled ? onClick : undefined}
      position="relative"
      border={isFeatured ? "2px solid" : "none"}
      borderColor="blue.500"
      boxShadow={isFeatured ? "0 0 15px rgba(66, 153, 225, 0.5)" : "none"}
    >
      <Image
        src={getChampionImageUrl(champion.name)}
        alt={champion.name}
        fallbackSrc="/control_ward.png"
        loading="lazy"
        filter={filter}
        opacity={opacity}
        w="100%"
      />
      {score !== undefined && score > 0.05 && !isLocked && (
         <Badge 
           position="absolute" 
           bottom={0} 
           right={0} 
           colorScheme="blue" 
           variant="solid" 
           fontSize={isFeatured ? "xs" : "2xs"}
           borderTopLeftRadius="md"
           px={isFeatured ? 2 : 1}
         >
           {Math.round(score * 100)}%
         </Badge>
      )}
      {isLocked && (
        <Box
          position="absolute"
          top={0}
          left={0}
          right={0}
          bottom={0}
          bg="rgba(0,0,0,0.2)"
        />
      )}
    </Box>
  );

  if (isFeatured) {
    return (
      <VStack align="stretch" spacing={2}>
        {cardContent}
        <Box 
          bg="gray.800" 
          p={2} 
          borderRadius="md" 
          border="1px solid" 
          borderColor="gray.700"
          minH="70px"
          display="flex"
          flexDirection="column"
        >
          <Text fontSize="xs" fontWeight="bold" color="blue.300" mb={1} isTruncated>
            {champion.name}
          </Text>
          {hints?.why ? (
            <Text 
              fontSize={hints.why.length > 40 ? "9px" : "10px"} 
              color="gray.300" 
              lineHeight="1.1" 
              noOfLines={4}
            >
              {hints.why}
            </Text>
          ) : (
            <Text fontSize="10px" color="gray.500" fontStyle="italic">
              Strategic choice
            </Text>
          )}
        </Box>
      </VStack>
    );
  }

  return (
    <Tooltip label={tooltipLabel} openDelay={300} hasArrow bg="gray.700">
      {cardContent}
    </Tooltip>
  );
}
