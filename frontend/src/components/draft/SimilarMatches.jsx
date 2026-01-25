import { 
  Box, 
  Text, 
  Badge, 
  Heading, 
  VStack,
  HStack,
  Spinner,
  Flex,
  Image,
  Spacer
} from "@chakra-ui/react";
import { useEffect, useState } from "react";
import Logo from "../Logo";
import { getChampionImageUrl } from "../../utils/champion";

export default function SimilarMatches({ draft }) {
  const [exactMatches, setExactMatches] = useState([]);
  const [similarDrafts, setSimilarDrafts] = useState([]);
  const [teamHistory, setTeamHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const allPicks = [
      ...draft.picks.blue,
      ...draft.picks.red
    ];

    if (allPicks.filter(Boolean).length === 10) {
      setLoading(true);
      fetch("/api/similar-matches/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          blue_team: draft.blue_team,
          red_team: draft.red_team,
          picks: draft.picks
        }),
      })
        .then((r) => r.json())
        .then((data) => {
          setExactMatches(data.exact_matches || []);
          setSimilarDrafts(data.similar_drafts || []);
          setTeamHistory(data.team_history || []);
          setLoading(false);
        })
        .catch((err) => {
          console.error("Failed to fetch similar matches", err);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [draft.picks, draft.blue_team, draft.red_team]);

  const allPicksCount = [
    ...draft.picks.blue,
    ...draft.picks.red
  ].filter(Boolean).length;

  if (allPicksCount < 10) return null;

  const renderMatchList = (matches, type = "exact") => (
    <VStack spacing={4} align="stretch">
      {matches.map((m, i) => {
        const isTeam1Blue = m.team_1_side?.toLowerCase() === 'blue';
        const blueTeamName = isTeam1Blue ? m.team_1 : m.team_2;
        const redTeamName = isTeam1Blue ? m.team_2 : m.team_1;
        const isBlueWin = m.winning_team === blueTeamName;
        const isRedWin = m.winning_team === redTeamName;

        const blueMatchCount = m.blue_picks.filter(p => p.is_match).length;
        const redMatchCount = m.red_picks.filter(p => p.is_match).length;

        return (
          <Box 
            key={i} 
            p={4} 
            borderRadius="xl" 
            bg={m.is_highlighted ? "blue.900" : "gray.900"} 
            border="1px solid" 
            borderColor={m.is_highlighted ? "blue.500" : "gray.700"}
            transition="all 0.2s"
            _hover={{ transform: "translateY(-2px)", boxShadow: "lg" }}
          >
            {/* Match Metadata Header */}
            <Flex justify="space-between" mb={4} borderBottom="1px solid" borderColor="gray.800" pb={2} align="center">
              <HStack spacing={3}>
                 <Logo name={m.tournament} type="tournament" size="18px" />
                 <Text fontSize="xs" fontWeight="black" color="blue.400" textTransform="uppercase">
                   {m.tournament}
                 </Text>
                 <Badge variant="outline" colorScheme="gray" fontSize="10px">
                   GAME {m.game_id}
                 </Badge>
                 {type === "similar" && (
                   <Badge colorScheme="purple" fontSize="10px">
                     {m.match_count}/10 MATCH
                   </Badge>
                 )}
                 {type === "team" && (
                   <Badge colorScheme="cyan" fontSize="10px">
                     {blueMatchCount >= 4 || redMatchCount >= 4 ? "TEAM COMP MATCH" : "PARTIAL MATCH"}
                   </Badge>
                 )}
              </HStack>
              <Text fontSize="xs" fontWeight="bold" color="gray.500" fontFamily="mono">
                {m.start_time ? new Date(m.start_time).toLocaleString([], { 
                  year: 'numeric', 
                  month: 'short', 
                  day: 'numeric', 
                  hour: '2-digit', 
                  minute: '2-digit' 
                }) : 'Unknown Date'}
              </Text>
            </Flex>

            {/* Competitors and Compositions - New Unified Layout */}
            <VStack spacing={4} align="stretch" w="100%">
              {/* Line 1: Team Info for both sides */}
              <Flex justify="space-between" align="center" w="100%">
                {/* Blue Team Info */}
                <HStack spacing={2} minW={{ base: "110px", md: "150px" }}>
                  <Text 
                    color={isBlueWin ? "green.400" : "red.400"} 
                    fontWeight="black" 
                    fontSize="2xs" 
                    w="42px" 
                    px={1} 
                    py={0.5} 
                    bg={isBlueWin ? "green.900" : "red.900"} 
                    borderRadius="sm"
                    textAlign="center"
                    whiteSpace="nowrap"
                  >
                    {isBlueWin ? "WIN" : "LOSS"}
                  </Text>
                  <Logo name={blueTeamName} size="24px" />
                  <Text fontSize="sm" fontWeight="black" color="blue.100" whiteSpace="nowrap" >{blueTeamName}</Text>
                </HStack>

                <Box textAlign="center">
                  <Text fontWeight="black" fontSize="10px" color="gray.600" letterSpacing="tighter">VS</Text>
                </Box>

                {/* Red Team Info */}
                <HStack spacing={2} minW={{ base: "110px", md: "150px" }} justify="flex-end">
                  <Text fontSize="sm" fontWeight="black" color="red.100" whiteSpace="nowrap" isTruncated maxW={{ base: "80px", md: "150px" }} textAlign="right">{redTeamName}</Text>
                  <Logo name={redTeamName} size="24px" />
                  <Text 
                    color={isRedWin ? "green.400" : "red.400"} 
                    fontWeight="black" 
                    fontSize="2xs" 
                    w="42px" 
                    px={1} 
                    py={0.5} 
                    bg={isRedWin ? "green.900" : "red.900"} 
                    borderRadius="sm"
                    textAlign="center"
                    whiteSpace="nowrap"
                  >
                    {isRedWin ? "WIN" : "LOSS"}
                  </Text>
                </HStack>
              </Flex>

              {/* Line 2: Picks for both sides */}
              <Flex justify="space-between" align="center" w="100%">
                {/* Blue Picks */}
                <HStack 
                  spacing={1} 
                  bg="blackAlpha.400" 
                  p={1} 
                  borderRadius="lg" 
                  border="1px solid" 
                  borderColor="blue.900"
                >
                  {m.blue_picks.map((c, idx) => (
                    <Image 
                      key={idx} 
                      src={getChampionImageUrl(c.name)} 
                      boxSize={{ base: "30px", md: "40px" }} 
                      borderRadius="sm" 
                      border="1px solid" 
                      borderColor="blue.600" 
                      boxShadow={c.is_match ? "0 0 8px 1px rgba(255, 255, 255, 0.4)" : "none"}
                      title={c.name}
                      flexShrink={0}
                    />
                  ))}
                </HStack>

                <Spacer />

                {/* Red Picks */}
                <HStack 
                  spacing={1} 
                  bg="blackAlpha.400" 
                  p={1} 
                  borderRadius="lg" 
                  border="1px solid" 
                  borderColor="red.900"
                >
                  {m.red_picks.map((c, idx) => (
                    <Image 
                      key={idx} 
                      src={getChampionImageUrl(c.name)} 
                      boxSize={{ base: "30px", md: "40px" }} 
                      borderRadius="sm" 
                      border="1px solid" 
                      borderColor="red.600" 
                      boxShadow={c.is_match ? "0 0 8px 1px rgba(255, 255, 255, 0.4)" : "none"}
                      title={c.name}
                      flexShrink={0}
                    />
                  ))}
                </HStack>
              </Flex>
            </VStack>
          </Box>
        );
      })}
    </VStack>
  );

  return (
    <VStack align="stretch" spacing={8} mt={8} w="100%">
      {/* Exact Matches Section */}
      <Box p={6} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="gray.700" boxShadow="2xl">
        <Heading size="sm" mb={6} color="blue.300" textTransform="uppercase" letterSpacing="widest">
          Exact Matches (10/10 Champions)
        </Heading>
        
        {loading ? (
          <HStack justify="center" py={10}>
            <Spinner size="md" color="blue.400" />
            <Text fontSize="sm" color="gray.400" ml={2}>Searching professional match history...</Text>
          </HStack>
        ) : exactMatches.length > 0 ? (
          renderMatchList(exactMatches, "exact")
        ) : (
          <Box py={10} textAlign="center" border="2px dashed" borderColor="gray.700" borderRadius="xl">
            <Text fontSize="sm" color="gray.500" fontStyle="italic">
              No professional matches found with this exact combination of 10 champions.
            </Text>
          </Box>
        )}
      </Box>

      {/* Team Composition History Section */}
      {teamHistory.length > 0 && (
        <Box p={6} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="gray.700" boxShadow="2xl">
          <Heading size="sm" mb={6} color="cyan.300" textTransform="uppercase" letterSpacing="widest">
            Team Composition History (4+ Team Picks)
          </Heading>
          {renderMatchList(teamHistory, "team")}
        </Box>
      )}

      {/* Similar Drafts Section */}
      <Box p={6} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="gray.700" boxShadow="2xl">
        <Heading size="sm" mb={6} color="purple.300" textTransform="uppercase" letterSpacing="widest">
          Similar Drafts (7+ Champions)
        </Heading>
        
        {loading ? (
          <HStack justify="center" py={10}>
            <Spinner size="md" color="purple.400" />
            <Text fontSize="sm" color="gray.400" ml={2}>Analyzing similar compositions...</Text>
          </HStack>
        ) : similarDrafts.length > 0 ? (
          renderMatchList(similarDrafts, "similar")
        ) : (
          <Box py={10} textAlign="center" border="2px dashed" borderColor="gray.700" borderRadius="xl">
            <Text fontSize="sm" color="gray.500" fontStyle="italic">
              No similar professional drafts found with 8 or 9 matching champions.
            </Text>
          </Box>
        )}
      </Box>
    </VStack>
  );
}
