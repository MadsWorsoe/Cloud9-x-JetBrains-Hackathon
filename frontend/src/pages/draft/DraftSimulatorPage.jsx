import { Box, VStack, Button, Container, Heading, Flex, Spacer, Text} from "@chakra-ui/react";
import { useNavigate } from "react-router-dom";
import { useMemo } from "react";
import DraftBoard from "../../components/draft/DraftBoard";
import useDraftAutosave from "../../hooks/useDraftAutosave";

export default function DraftSimulatorPage({ draft, setDraft }) {
  const navigate = useNavigate();

  // 🔥 THIS is where autosave is activated
  useDraftAutosave(draft);

  function startNewDraft() {
    fetch("/api/drafts/", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        navigate(`/draft/${data.id}`, { replace: true });
        setDraft(data.draft);
      });
  }

  function copyToNewSession() {
    fetch("/api/drafts/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        blue_team: draft.blue_team,
        red_team: draft.red_team,
        picks: draft.picks,
        bans: draft.bans,
      }),
    })
      .then((r) => r.json())
      .then((data) => {
        window.open(`/draft/${data.id}`, "_blank");
      });
  }

  const isStarted = useMemo(() => [
    ...draft.picks.blue,
    ...draft.picks.red,
    ...draft.bans.blue,
    ...draft.bans.red
  ].some(Boolean), [draft]);

  const isComplete = useMemo(() => [
    ...draft.picks.blue,
    ...draft.picks.red,
    ...draft.bans.blue,
    ...draft.bans.red
  ].filter(Boolean).length >= 20, [draft]);

  return (
    <Container maxW="container.xl" py={{ base: 2, md: 4 }} px={{ base: 2, md: 4 }}>
      <VStack spacing={{ base: 2, md: 4 }} align="stretch">
        {!isStarted ? (
          <Flex align="center">
            <Heading size={{ base: "md", md: "lg" }}>Draft Simulator</Heading>
            <Spacer />
              <Text>Think you can draft better than the Pros?
                <Spacer />
                  Test out your drafting skills below.
                <Spacer />
                  The simulator will recommend picks and bans based on team's actual bans in their 2024 & 2025 games.
                <Spacer />
                  Think you did it better? Share your draft with friends afterwards
              </Text>
            <Spacer />
            <Button colorScheme="blue" size={{ base: "sm", md: "md" }} onClick={startNewDraft}>
              New Draft
            </Button>
          </Flex>
        ) : (
          <Flex align="center" px={4} py={2} >
             <Spacer />
             {!isComplete && (
               <Button colorScheme="teal" variant="outline" size="sm" onClick={copyToNewSession} leftIcon={<Text fontSize="lg">📋</Text>}>
                  Copy Draft to New Window
               </Button>
             )}
          </Flex>
        )}

        <DraftBoard 
          draft={draft} 
          setDraft={setDraft} 
          startNewDraft={startNewDraft} 
          copyToNewSession={copyToNewSession} 
        />
      </VStack>
    </Container>
  );
}
