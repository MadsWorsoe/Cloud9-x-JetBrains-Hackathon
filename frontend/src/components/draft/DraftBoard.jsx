import { Grid, GridItem, Box, Text, Center, useBreakpointValue, HStack, VStack, Flex, Divider, Image, Heading, Button, useToast, Select } from "@chakra-ui/react";
import PickColumn from "./PickColumn";
import BanRow from "./BanRow";
import PickRow from "./PickRow";
import ChampionGrid from "./ChampionGrid";
import TeamSelector from "./TeamSelector";
import DraftInsights from "./DraftInsights";
import SimilarMatches from "./SimilarMatches";
import Logo from "../Logo";
import { DRAFT_PHASES } from "../../constants/draft";
import { useEffect, useState, useMemo } from "react";
import { fetchWithCache } from "../../utils/apiCache";
import { getChampionImageUrl } from "../../utils/champion";

export default function DraftBoard({ draft, setDraft, startNewDraft, copyToNewSession }) {
  const [recommendations, setRecommendations] = useState([]);
  const [insights, setInsights] = useState(null);
  const [teams, setTeams] = useState([]);
  const [allChampions, setAllChampions] = useState([]);
  const [modelVersion, setModelVersion] = useState("v3");
  const [isSelecting, setIsSelecting] = useState(false);
  const isMobile = useBreakpointValue({ base: true, lg: false });
  const toast = useToast();
  
  if (!draft) return null;

  useEffect(() => {
    fetchWithCache("/api/teams/")
      .then(setTeams)
      .catch(console.error);
    
    fetchWithCache("/api/champions/")
      .then(setAllChampions)
      .catch(console.error);
  }, []);

  const blueTeam = teams.find(t => t.external_id === draft.blue_team || t.name === draft.blue_team);
  const redTeam = teams.find(t => t.external_id === draft.red_team || t.name === draft.red_team);

  // Enrich picks with full champion data (including roles) from the master list
  const enrichedPicks = useMemo(() => {
    const enrich = (sidePicks = []) => sidePicks.map(p => {
      if (!p) return null;
      // If p already has roles, we can use it, but checking allChampions is safer for old data
      const full = allChampions.find(c => c.id === p.id || c.name === p.name);
      return full ? { ...p, ...full } : p;
    });
    
    return {
      blue: enrich(draft.picks?.blue).map(p => p ? { ...p, stats: draft.stats?.blue?.[p?.id] } : null),
      red: enrich(draft.picks?.red).map(p => p ? { ...p, stats: draft.stats?.red?.[p?.id] } : null)
    };
  }, [draft.picks, draft.stats, allChampions]);

  const enrichedBans = useMemo(() => {
    const enrich = (sideBans = [], side) => sideBans.map(b => {
      if (!b) return null;
      const full = allChampions.find(c => c.id === b.id || c.name === b.name);
      const stats = draft.ban_stats?.[side]?.[b?.id];
      return full ? { ...b, ...full, stats } : { ...b, stats };
    });

    return {
      blue: enrich(draft.bans?.blue, "blue"),
      red: enrich(draft.bans?.red, "red")
    };
  }, [draft.bans, draft.ban_stats, allChampions]);

  const teamsSelected = draft.blue_team && draft.red_team;

  useEffect(() => {
    if (teamsSelected) {
      fetchWithCache("/api/recommendations/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          draft_id: draft.id,
          blue_team: draft.blue_team,
          red_team: draft.red_team,
          picks: draft.picks,
          bans: draft.bans,
          model: modelVersion,
        }),
      })
        .then((data) => {
          if (data.recommendations) {
            setRecommendations(data.recommendations);
          }
          if (data.insights) {
            setInsights(data.insights);
          }
          setIsSelecting(false);
        })
        .catch((err) => {
          console.error("Failed to fetch recommendations", err);
          setIsSelecting(false);
        });
    } else {
      setRecommendations([]);
      setInsights(null);
      setIsSelecting(false);
    }
  }, [draft.id, draft.blue_team, draft.red_team, draft.picks, draft.bans, teamsSelected, modelVersion]);

  // Calculate current step based on filled slots
  const allSelected = useMemo(() => [
    ...draft.picks.blue,
    ...draft.picks.red,
    ...draft.bans.blue,
    ...draft.bans.red
  ].filter(Boolean), [draft.picks, draft.bans]);

  const totalActions = allSelected.length;
  const isComplete = totalActions >= DRAFT_PHASES.length;
  const [currentSide, currentAction] = isComplete ? [null, null] : DRAFT_PHASES[totalActions];

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href);
    toast({
      title: "Link copied!",
      description: "Draft link has been copied to clipboard.",
      status: "success",
      duration: 2000,
      isClosable: true,
      position: "top",
    });
  };

  const handleSelectChampion = (champion) => {
    if (!teamsSelected) return;
    if (isComplete) return;
    if (isSelecting) return;

    // Check if champion already selected or banned
    if (allSelected.some(c => c && c.id === champion.id)) return;

    setIsSelecting(true);
    const side = currentSide;
    const action = currentAction;
    const isPick = action === 'pick';
    const currentList = isPick ? draft.picks[side] : draft.bans[side];
    const firstNull = currentList.indexOf(null);
    
    if (firstNull !== -1) {
      const newList = [...currentList];
      newList[firstNull] = champion;
      
      const isLastPick = totalActions === DRAFT_PHASES.length - 1;
      
      const newPicks = {
        ...draft.picks,
        [side]: isPick ? newList : draft.picks[side]
      };
      const newBans = {
        ...draft.bans,
        [side]: !isPick ? newList : draft.bans[side]
      };

      // Persist to backend
      fetch(`/api/drafts/${draft.id}/update/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          picks: newPicks,
          bans: newBans,
          status: isLastPick ? "COMPLETED" : draft.status
        }),
      })
        .then(res => res.json())
        .then(updatedDraft => {
          setDraft(updatedDraft);
          setIsSelecting(false);
        })
        .catch(err => {
          console.error("Failed to update draft", err);
          setIsSelecting(false);
          toast({
            title: "Connection Error",
            description: "Failed to save selection. Please try again.",
            status: "error",
            duration: 3000,
            isClosable: true,
          });
        });
    }
  };

  if (isMobile) {
    if (!teamsSelected) {
      return (
        <VStack spacing={4} py={4} w="100%">
          <Heading size="md" color="gray.400">Select Teams to Start</Heading>
          
          <Box w="100%" p={4} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="blue.500">
            <TeamSelector side="blue" draft={draft} setDraft={setDraft} />
          </Box>

          <Center h="20px" w="100%">
            <Divider />
            <Text fontWeight="black" fontSize="xl" color="gray.600" mx={4}>VS</Text>
            <Divider />
          </Center>

          <Box w="100%" p={4} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="red.500">
            <TeamSelector side="red" draft={draft} setDraft={setDraft} />
          </Box>
          
          <Text color="blue.300" fontSize="sm" textAlign="center" px={6}>
            Choose both teams above to unlock the champion selection grid.
          </Text>
        </VStack>
      );
    }

    const isBlueActing = currentSide === "blue";
    const sideColor = isBlueActing ? "blue.400" : (currentSide === "red" ? "red.400" : "gray.500");

    return (
      <VStack spacing={4} align="stretch" w="100%">
        
        {/* Compact Header */}
        <Box 
          bg="gray.800" 
          p={3} 
          borderRadius="lg" 
          boxShadow="xl"
          borderBottom="4px solid"
          borderColor={sideColor}
          position="sticky"
          top="72px"
          zIndex={20}
        >
          <Flex align="center" justify="space-between" mb={2}>
            <HStack spacing={2} flex={1}>
              <Logo name={blueTeam?.name} size="32px" />
              <Text fontSize="xs" fontWeight="bold" isTruncated maxW="70px">{blueTeam?.name || "Blue"}</Text>
            </HStack>

            <VStack spacing={0} flex={2}>
              <Text fontSize="10px" fontWeight="bold" color="gray.500" textTransform="uppercase">
                 {isComplete ? "Draft Finished" : `${currentAction} Phase`}
              </Text>
              {!isComplete && (
                <Text fontSize="sm" fontWeight="black" color={sideColor} textAlign="center">
                   {currentSide.toUpperCase()} {currentAction.toUpperCase()}
                </Text>
              )}
            </VStack>

            <HStack spacing={2} flex={1} justify="flex-end">
              <Text fontSize="xs" fontWeight="bold" isTruncated maxW="70px">{redTeam?.name || "Red"}</Text>
              <Logo name={redTeam?.name} size="32px" />
            </HStack>
          </Flex>
          
            <VStack spacing={3} align="stretch">
              <HStack justify="space-between" align="start" px={1}>
                <BanRow 
                  side="blue" 
                  bans={enrichedBans.blue} 
                  isActing={currentSide === "blue" && currentAction === "ban"} 
                  isCompact 
                  isComplete={isComplete} 
                  opponentName={redTeam?.name}
                  teamName={blueTeam?.name}
                />
                <BanRow 
                  side="red" 
                  bans={enrichedBans.red} 
                  isActing={currentSide === "red" && currentAction === "ban"} 
                  isCompact 
                  isComplete={isComplete} 
                  opponentName={blueTeam?.name}
                  teamName={redTeam?.name}
                />
              </HStack>
              
              <Divider borderColor="gray.700" opacity={0.5} />

              <HStack spacing={1} justify="space-between" align="start">
                <PickRow side="blue" picks={enrichedPicks.blue} isActing={currentSide === "blue" && currentAction === "pick"} isCompact isComplete={isComplete} />
                <PickRow side="red" picks={enrichedPicks.red} isActing={currentSide === "red" && currentAction === "pick"} isCompact isComplete={isComplete} />
              </HStack>
            </VStack>
        </Box>

        {insights && !isComplete && (
          <DraftInsights 
            insights={insights} 
            blueTeamName={blueTeam?.name} 
            redTeamName={redTeam?.name} 
          />
        )}

        {isComplete && (
          <VStack spacing={6} align="stretch" mt={2}>
            <VStack spacing={6} py={10} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="gray.700" justify="center">
              <VStack spacing={1}>
                <Heading size="md" color="blue.400">Draft Complete</Heading>
                <Text color="gray.400" fontSize="sm">All picks and bans are finalized.</Text>
              </VStack>
              <HStack spacing={4}>
                <Button colorScheme="blue" size="md" onClick={startNewDraft} px={6}>
                  New Draft
                </Button>
                <Button colorScheme="gray" size="md" onClick={handleShare} px={6}>
                  Share Draft
                </Button>
              </HStack>
            </VStack>
            <SimilarMatches draft={draft} />
          </VStack>
        )}
      </VStack>
    );
  }

  return (
    <Box w="100%">
      
      <Grid
        w="100%"
        templateColumns={{
          base: "1fr",
          lg: "240px 1fr 240px",
        }}
        gap={4}
        alignItems="start"
      >
      <GridItem>
        <TeamSelector side="blue" draft={draft} setDraft={setDraft} />
        <BanRow 
          side="blue" 
          bans={enrichedBans.blue} 
          isActing={teamsSelected && currentSide === "blue" && currentAction === "ban"}
          isComplete={isComplete}
          opponentName={redTeam?.name}
          teamName={blueTeam?.name}
        />
        <Divider my={6} borderColor="gray.700" />
        <PickColumn 
          side="Blue" 
          picks={enrichedPicks.blue} 
          isActing={teamsSelected && currentSide === "blue" && currentAction === "pick"}
          isComplete={isComplete}
        />
      </GridItem>

      <GridItem position="relative">
        {!teamsSelected && (
          <Center
            position="absolute"
            top={0}
            left={0}
            right={0}
            bottom={0}
            bg="rgba(0,0,0,0.7)"
            zIndex={10}
            borderRadius="md"
            flexDirection="column"
            p={4}
            textAlign="center"
          >
            <Text color="white" fontWeight="bold" fontSize="lg">
              Select both teams to start the draft
            </Text>
          </Center>
        )}
        
        {insights && !isComplete && (
          <DraftInsights 
            insights={insights} 
            blueTeamName={blueTeam?.name} 
            redTeamName={redTeam?.name} 
          />
        )}

        {!isComplete ? (
          <ChampionGrid 
            onSelectChampion={handleSelectChampion} 
            allSelected={allSelected}
            recommendations={recommendations}
            isComplete={isComplete}
            isSelecting={isSelecting}
          />
        ) : (
          <VStack spacing={8} align="stretch" h="100%">
            <VStack spacing={8} py={20} bg="gray.800" borderRadius="xl" border="1px solid" borderColor="gray.700" justify="center">
              <VStack spacing={2}>
                <Heading size="xl" color="blue.400">Draft Complete</Heading>
                <Text color="gray.400">All picks and bans are finalized.</Text>
              </VStack>
              <HStack spacing={4}>
                <Button colorScheme="blue" size="lg" onClick={startNewDraft} px={10}>
                  New Draft
                </Button>
                <Button colorScheme="gray" size="lg" onClick={handleShare} px={10}>
                  Share Draft
                </Button>
              </HStack>
            </VStack>
            <SimilarMatches draft={draft} />
          </VStack>
        )}
      </GridItem>

      <GridItem>
        <TeamSelector side="red" draft={draft} setDraft={setDraft} />
        <BanRow 
          side="red" 
          bans={enrichedBans.red} 
          isActing={teamsSelected && currentSide === "red" && currentAction === "ban"}
          isComplete={isComplete}
          opponentName={blueTeam?.name}
          teamName={redTeam?.name}
        />
        <Divider my={6} borderColor="gray.700" />
        <PickColumn 
          side="Red" 
          picks={enrichedPicks.red} 
          isActing={teamsSelected && currentSide === "red" && currentAction === "pick"}
          isComplete={isComplete}
        />
      </GridItem>
    </Grid>
    </Box>
  );
}
