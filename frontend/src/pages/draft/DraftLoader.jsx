import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import DraftSimulatorPage from "./DraftSimulatorPage";
import { Box, Spinner, Center } from "@chakra-ui/react";

export default function DraftLoader() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // If we already have the draft with the correct ID, don't show loader or fetch again
    if (draft && draft.id === id) {
      setLoading(false);
      return;
    }

    setDraft(null); // Clear old draft to avoid flicker
    setLoading(true);
    if (!id) {
      // Create silently
      fetch("/api/drafts/", { method: "POST" })
        .then((r) => r.json())
        .then((data) => {
          navigate(`/draft/${data.id}`, { replace: true });
          setDraft(data.draft);
          setLoading(false);
        });
    } else {
      fetch(`/api/drafts/${id}/`)
        .then((r) => r.json())
        .then((data) => {
          setDraft(data);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    }
  }, [id, navigate, draft?.id]);

  return (
    <Box position="relative" w="100%">
      {loading && !draft ? (
        <Center py={20}>
          <Spinner size="xl" color="blue.500" />
        </Center>
      ) : (
        <DraftSimulatorPage
          draft={draft}
          setDraft={setDraft}
        />
      )}
    </Box>
  );
}
