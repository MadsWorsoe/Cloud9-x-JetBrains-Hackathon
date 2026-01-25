import {
  Box,
  Text,
  HStack,
  VStack,
  Badge,
  Heading,
  SimpleGrid,
  Tooltip,
} from "@chakra-ui/react";
import { InfoIcon, WarningIcon } from "@chakra-ui/icons";

export default function DraftInsights({ insights, blueTeamName, redTeamName }) {
  if (!insights) return null;

  const {
    urgency,
    urgent_champ,
    missing_roles,
    team_intent,
    forced,
  } = insights;

  const blueIntent = team_intent?.blue || [];
  const redIntent = team_intent?.red || [];
  const blueMissing = missing_roles?.blue || [];
  const redMissing = missing_roles?.red || [];

  const contestedPicks = blueIntent.filter(b => 
    redIntent.some(r => r.name === b.name)
  ).map(b => {
    const redMatch = redIntent.find(r => r.name === b.name);
    return {
      ...b,
      redProb: redMatch ? redMatch.prob : 0
    };
  });
  
  const blueOnly = blueIntent.filter(b => 
    !redIntent.some(r => r.name === b.name)
  );
  
  const redOnly = redIntent.filter(r => 
    !blueIntent.some(b => b.name === r.name)
  );

  const urgencyExplanation = "This indicates a champion that is critical for your team's strategy and is also highly valued by the opponent. If you don't pick it now, the opponent likely will, significantly lowering your win probability.";

  return (
    <Box
      bg="gray.800"
      p={4}
      borderRadius="xl"
      border="1px solid"
      borderColor="gray.700"
      mb={4}
      boxShadow="lg"
      position="relative"
      overflow="hidden"
    >
      <Box 
        position="absolute" 
        top={0} 
        left={0} 
        w="4px" 
        h="100%" 
        bg="blue.500" 
      />
      <HStack justify="space-between" mb={4} align="start">
        <HStack>
          <InfoIcon color="blue.400" />
          <Heading size="xs" textTransform="uppercase" color="gray.400" letterSpacing="wider">
            Strategic Insights
          </Heading>
        </HStack>

        {/* Urgency & Risk - Moved to top left across from title */}
        <VStack align="end" spacing={0}>
          <HStack spacing={1}>
            <WarningIcon w={3} h={3} color="orange.400" />
            <Text fontSize="2xs" fontWeight="bold" color="gray.500" textTransform="uppercase">
              Urgency
            </Text>
            {urgency.includes("Urgent") && (
              <Tooltip label={urgencyExplanation} hasArrow>
                <InfoIcon w={3} h={3} color="gray.500" />
              </Tooltip>
            )}
          </HStack>
          <Text fontSize="sm" fontWeight="bold" color={urgency.includes("Urgent") ? "red.400" : "white"}>
            {urgency}
            {urgent_champ && <Text as="span" ml={2} fontSize="xs" color="gray.300">({urgent_champ})</Text>}
          </Text>
          {forced === "Yes" && (
            <Badge colorScheme="red" variant="solid" fontSize="2xs">
              BEING FORCED
            </Badge>
          )}
        </VStack>
      </HStack>

      <SimpleGrid columns={{ base: 1, md: 3 }} spacing={8}>
        {/* Blue Side Wants */}
        <VStack align="start" spacing={3}>
          <VStack align="start" spacing={1} w="100%">
            <Text fontSize="xs" fontWeight="black" color="blue.400" textTransform="uppercase" letterSpacing="widest">
              {blueTeamName || "Blue Side"} Intent
            </Text>
            {blueMissing.length > 0 && (
              <HStack spacing={1} wrap="wrap">
                {blueMissing.map(role => (
                  <Badge key={role} colorScheme="blue" variant="outline" fontSize="3xs" py={0} px={1}>
                    {role}
                  </Badge>
                ))}
              </HStack>
            )}
          </VStack>
          <VStack align="start" spacing={2} w="100%">
            {blueOnly.length > 0 ? blueOnly.map((setup, i) => (
              <HStack key={i} justify="space-between" w="100%" bg="blue.900" p={2} borderRadius="md" borderLeft="4px solid" borderColor="blue.500">
                <Text fontSize="sm" color="blue.50" fontWeight="bold">{setup.name}</Text>
                <Badge colorScheme="blue" variant="subtle">{(setup.prob * 100).toFixed(0)}%</Badge>
              </HStack>
            )) : <Text fontSize="sm" color="gray.500">No unique blue picks</Text>}
          </VStack>
        </VStack>

        {/* Contested Picks */}
        <VStack align="center" spacing={3}>
          <Text fontSize="xs" fontWeight="black" color="purple.400" textTransform="uppercase" letterSpacing="widest">
            Contested
          </Text>
          <VStack align="stretch" spacing={2} w="100%">
            {contestedPicks.length > 0 ? contestedPicks.map((setup, i) => (
              <Box key={i} bg="purple.900" p={2} borderRadius="md" borderY="1px solid" borderColor="purple.500" textAlign="center">
                <Text fontSize="sm" color="purple.50" fontWeight="bold">{setup.name}</Text>
                <HStack justify="center" spacing={2}>
                  <Badge colorScheme="blue" variant="subtle" fontSize="2xs">Blue: {(setup.prob * 100).toFixed(0)}%</Badge>
                  <Badge colorScheme="red" variant="subtle" fontSize="2xs">Red: {(setup.redProb * 100).toFixed(0)}%</Badge>
                </HStack>
              </Box>
            )) : <Text fontSize="sm" color="gray.500" textAlign="center">No contested picks</Text>}
          </VStack>
        </VStack>

        {/* Red Side Wants */}
        <VStack align="end" spacing={3}>
          <VStack align="end" spacing={1} w="100%">
            <Text fontSize="xs" fontWeight="black" color="red.400" textTransform="uppercase" letterSpacing="widest">
              {redTeamName || "Red Side"} Intent
            </Text>
            {redMissing.length > 0 && (
              <HStack spacing={1} wrap="wrap" justify="end">
                {redMissing.map(role => (
                  <Badge key={role} colorScheme="red" variant="outline" fontSize="3xs" py={0} px={1}>
                    {role}
                  </Badge>
                ))}
              </HStack>
            )}
          </VStack>
          <VStack align="end" spacing={2} w="100%">
            {redOnly.length > 0 ? redOnly.map((setup, i) => (
              <HStack key={i} justify="space-between" w="100%" bg="red.900" p={2} borderRadius="md" borderRight="4px solid" borderColor="red.500">
                <Badge colorScheme="red" variant="subtle">{(setup.prob * 100).toFixed(0)}%</Badge>
                <Text fontSize="sm" color="red.50" fontWeight="bold">{setup.name}</Text>
              </HStack>
            )) : <Text fontSize="sm" color="gray.500">No unique red picks</Text>}
          </VStack>
        </VStack>
      </SimpleGrid>
    </Box>
  );
}
