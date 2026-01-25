import {
  Box,
  VStack,
  Text,
  Spinner,
  HStack,
  Input,
  Divider,
  useDisclosure,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import { useState, useEffect, useRef, useMemo } from "react";
import Logo from "../Logo";
import { fetchWithCache } from "../../utils/apiCache";

export default function TeamSelector({ side, draft, setDraft }) {
  const sideColor = side === "blue" ? "blue.500" : "red.500";
  const [loading, setLoading] = useState(false);
  const [teams, setTeams] = useState([]);
  const [fetchingTeams, setFetchingTeams] = useState(true);
  const [search, setSearch] = useState("");
  const { isOpen, onOpen, onClose } = useDisclosure();
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const handleClose = () => {
    onClose();
    setSearch("");
  };

  useEffect(() => {
    fetchWithCache("/api/teams/")
      .then((data) => {
        setTeams(data);
        setFetchingTeams(false);
      })
      .catch(() => setFetchingTeams(false));
  }, []);

  const draftStarted = useMemo(() => [
    ...(draft.picks?.blue || []),
    ...(draft.picks?.red || []),
    ...(draft.bans?.blue || []),
    ...(draft.bans?.red || []),
  ].some((id) => id !== null), [draft.picks, draft.bans]);

  const currentTeamId = side === "blue" ? draft.blue_team : draft.red_team;
  const selectedTeam = useMemo(() => 
    teams.find(t => t.external_id === currentTeamId || t.name === currentTeamId),
    [teams, currentTeamId]
  );

  const filteredTeams = useMemo(() => 
    teams.filter(t => t.name?.toLowerCase().includes(search.toLowerCase())),
    [teams, search]
  );

  function update(team) {
    if (draftStarted) return;
    setLoading(true);
    const field = side === "blue" ? "blue_team" : "red_team";
    
    // Persist to backend
    fetch(`/api/drafts/${draft.id}/update/`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        [field]: team.external_id
      }),
    })
      .then(res => res.json())
      .then(updatedDraft => {
        setDraft(updatedDraft);
        setSearch("");
        onClose();
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to update team", err);
        setLoading(false);
      });
  }

  const handleScroll = () => {
    if (document.activeElement === inputRef.current) {
      // Remove text selection (highlight) but keep focus
      const len = inputRef.current.value.length;
      inputRef.current.setSelectionRange(len, len);
    }
  };

  return (
    <VStack w="100%" align="stretch" spacing={2} mb={4}>
      <HStack justify="space-between" align="center" px={1}>
        <Text fontWeight="extrabold" fontSize="xs" textTransform="uppercase" color={sideColor} letterSpacing="wider">
          {side} Side
        </Text>
        {(loading || fetchingTeams) && <Spinner size="xs" color="blue.400" />}
      </HStack>
      
      <Box position="relative">
        <HStack 
          bg="gray.800" 
          border="1px solid" 
          borderColor={isOpen ? "blue.400" : "gray.700"}
          borderRadius="lg"
          px={3}
          height="48px"
          spacing={2}
          _hover={{ borderColor: "blue.400" }}
          boxShadow={isOpen ? "0 0 0 1px var(--chakra-colors-blue-400)" : "none"}
          transition="all 0.2s"
          onClick={() => {
            if (!isOpen) onOpen();
            inputRef.current?.focus();
          }}
          cursor="text"
        >
          {selectedTeam && !search && (
            <Logo name={selectedTeam.name} size="24px" mx={0} />
          )}
          <Input 
            ref={inputRef}
            variant="unstyled"
            placeholder={selectedTeam ? selectedTeam.name : "Search team..."}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              if (!isOpen) onOpen();
            }}
            onFocus={() => {
              onOpen();
              if (selectedTeam && !search) {
                setSearch(selectedTeam.name);
              }
              setTimeout(() => inputRef.current?.select(), 0);
            }}
            fontSize="md"
            fontWeight="semibold"
            isDisabled={draftStarted || fetchingTeams}
            _disabled={{ opacity: 0.8, cursor: "not-allowed" }}
          />
          <ChevronDownIcon color="gray.500" />
        </HStack>

        {isOpen && (
          <Box 
            position="absolute" 
            top="100%" 
            left={0} 
            right={0} 
            zIndex={30} 
            bg="gray.800" 
            borderColor="gray.700" 
            borderWidth="1px"
            borderRadius="lg"
            mt={1}
            maxH="300px" 
            overflowY="auto"
            boxShadow="2xl"
            p={1}
            ref={listRef}
            onScroll={handleScroll}
          >
            {filteredTeams.length > 0 ? (
              filteredTeams.map((t, idx) => {
                const prevTeam = idx > 0 ? filteredTeams[idx-1] : null;
                const showDivider = prevTeam && prevTeam.draft_action_count > 1000 && t.draft_action_count <= 1000 && !search;
                
                return (
                  <Box key={t.id}>
                    {showDivider && (
                      <Box px={3} py={2}>
                        <Divider borderColor="gray.600" />
                        <Text fontSize="10px" color="gray.500" mt={2} fontWeight="bold">OTHER TEAMS</Text>
                      </Box>
                    )}
                    <Box
                      onClick={(e) => {
                        e.stopPropagation();
                        update(t);
                      }}
                      bg="gray.800"
                      _hover={{ bg: "gray.700", color: "blue.300" }}
                      px={3}
                      py={2}
                      borderRadius="md"
                      mb={1}
                      cursor="pointer"
                    >
                      <HStack spacing={3}>
                        <Logo name={t.name} size="24px" mx={0} />
                        <Text fontSize="sm" fontWeight="medium">{t.name}</Text>
                      </HStack>
                    </Box>
                  </Box>
                )
              })
            ) : (
              <Text p={4} textAlign="center" color="gray.500" fontSize="sm">No teams found</Text>
            )}
          </Box>
        )}
      </Box>
      {isOpen && (
        <Box 
          position="fixed" 
          top={0} 
          left={0} 
          right={0} 
          bottom={0} 
          zIndex={20} 
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }} 
        />
      )}
    </VStack>
  );
}
