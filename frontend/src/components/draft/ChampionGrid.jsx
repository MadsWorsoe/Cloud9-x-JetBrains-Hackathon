import {
  Box,
  Input,
  SimpleGrid,
  Spinner,
  VStack,
  Text,
} from "@chakra-ui/react"
import { useEffect, useMemo, useState } from "react"
import { ChampionCard } from "./ChampionCard"
import { fetchWithCache } from "../../utils/apiCache"
import { getChampionImageUrl } from "../../utils/champion"

export default function ChampionGrid({ onSelectChampion, allSelected = [], recommendations = [], isComplete, isSelecting }) {
  const [champions, setChampions] = useState([])
  const [search, setSearch] = useState("")
  const [loading, setLoading] = useState(true)

  const selectedIds = useMemo(() => new Set(allSelected.map((c) => c.id)), [allSelected])

  useEffect(() => {
    fetchWithCache("/api/champions/")
      .then((data) => {
        setChampions(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const sortedChampions = useMemo(() => {
    if (recommendations && recommendations.length > 0) {
      // Create a map for quick lookup
      const scoreMap = new Map(recommendations.map(r => [r.champion_id, r.score]));
      
      return [...champions].sort((a, b) => {
        // First priority: unlocked champions first
        const isLockedA = selectedIds.has(a.id);
        const isLockedB = selectedIds.has(b.id);
        if (isLockedA !== isLockedB) {
          return isLockedA ? 1 : -1;
        }

        // Second priority: score
        const scoreA = scoreMap.get(a.id) ?? -1;
        const scoreB = scoreMap.get(b.id) ?? -1;
        
        if (scoreA !== scoreB) {
          return scoreB - scoreA; // Descending
        }
        return a.name.localeCompare(b.name);
      });
    }
    
    // Default alphabetical, but still respect locked status
    return [...champions].sort((a, b) => {
      const isLockedA = selectedIds.has(a.id);
      const isLockedB = selectedIds.has(b.id);
      if (isLockedA !== isLockedB) {
        return isLockedA ? 1 : -1;
      }
      return a.name.localeCompare(b.name);
    });
  }, [champions, recommendations, selectedIds]);

  const filteredChampions = useMemo(() => {
    const q = search.toLowerCase()
    return sortedChampions.filter((c) =>
      c.name.toLowerCase().includes(q)
    )
  }, [sortedChampions, search])

  const top10 = useMemo(() => {
    if (search || recommendations.length === 0 || isComplete) return [];
    return filteredChampions.slice(0, 10);
  }, [filteredChampions, search, recommendations, isComplete]);

  const others = useMemo(() => {
    if (search || recommendations.length === 0 || isComplete) return filteredChampions;
    return filteredChampions.slice(10);
  }, [filteredChampions, search, recommendations, isComplete]);

  return (
    <VStack align="stretch" spacing={4} h="100%">
      <Input
        placeholder="Search champion..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        size="md"
        bg="gray.800"
        borderColor="gray.700"
        _hover={{ borderColor: "blue.400" }}
        _focus={{ borderColor: "blue.400", boxShadow: "0 0 0 1px var(--chakra-colors-blue-400)" }}
        borderRadius="lg"
      />

      <Box flex="1" overflowY="auto" px={1}>
        {loading ? (
          <Box textAlign="center" pt={10}>
            <Spinner />
          </Box>
        ) : (
          <VStack align="stretch" spacing={6}>
            {top10.length > 0 && (
              <Box>
                <Text fontSize="xs" fontWeight="bold" color="blue.400" mb={3} textTransform="uppercase" letterSpacing="wider">
                  Top Recommendations
                </Text>
                <SimpleGrid columns={{ base: 2, sm: 3, md: 5 }} spacing={4}>
                  {top10.map((champion) => (
                    <ChampionCard
                      key={champion.id}
                      champion={champion}
                      isLocked={selectedIds.has(champion.id)}
                      onClick={() => {
                        onSelectChampion(champion)
                        setSearch("")
                      }}
                      score={recommendations?.find(r => r.champion_id === champion.id)?.score}
                      hints={recommendations?.find(r => r.champion_id === champion.id)?.hints}
                      isComplete={isComplete}
                      isSelecting={isSelecting}
                      isFeatured={true}
                    />
                  ))}
                </SimpleGrid>
              </Box>
            )}

            <Box>
              {top10.length > 0 && (
                <Text fontSize="xs" fontWeight="bold" color="gray.500" mb={3} textTransform="uppercase" letterSpacing="wider">
                  Other Champions
                </Text>
              )}
              <SimpleGrid columns={{ base: 4, sm: 5, md: 6, lg: 8 }} spacing={2}>
                {others.map((champion) => (
                  <ChampionCard
                    key={champion.id}
                    champion={champion}
                    isLocked={selectedIds.has(champion.id)}
                    onClick={() => {
                      onSelectChampion(champion)
                      setSearch("")
                    }}
                    score={recommendations?.find(r => r.champion_id === champion.id)?.score}
                    hints={recommendations?.find(r => r.champion_id === champion.id)?.hints}
                    isComplete={isComplete}
                    isSelecting={isSelecting}
                  />
                ))}
              </SimpleGrid>
            </Box>
          </VStack>
        )}

        {!loading && filteredChampions.length === 0 && (
          <Text textAlign="center" mt={6} fontSize="sm" color="gray.400">
            No champions found
          </Text>
        )}
      </Box>
    </VStack>
  )
}
