import React from "react";
import {
  ChakraProvider,
  Box,
  VStack,
  Text,
  Link as ChakraLink,
  HStack,
  Button,
} from "@chakra-ui/react";
import { BrowserRouter as Router, Routes, Route, Link as RouterLink } from "react-router-dom";
import { motion } from "framer-motion";

// Components
import Header from "./src/components/Header";
import Footer from "./src/components/Footer";
import AssetPreloader from "./src/components/AssetPreloader";
import Seo from "./src/components/Seo";
import { HelmetProvider, Helmet } from "react-helmet-async";

// Pages / Views
import GameViewer from "./src/components/GameViewer";
import DemoViewer from "./src/components/DemoViewer";
import MatchList from "./src/components/MatchList";
import TeamPage from "./src/pages/TeamPage";
import TeamList from "./src/pages/TeamList";
import TeamDemoPage from "./src/pages/TeamDemoPage";
import PlayerDemoPage from "./src/pages/PlayerDemoPage";
import DraftLoader from "./src/pages/draft/DraftLoader";
import BlogPost from "./src/pages/blog/BlogPost";
import BlogList from "./src/pages/blog/BlogList";

// Motion wrappers
const MotionBox = motion(Box);
const MotionHeading = motion(Text); // or Heading if you prefer

function Home() {
  return (
    <VStack spacing={8} textAlign="center" px={6} py={10} w="100%">
      <MotionHeading
        as="h1"
        fontSize={{ base: "3xl", md: "5xl" }}
        fontWeight="extrabold"
        color="white"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
      >
        <HStack spacing={3} justify="center">
          <Text as="span" color="blue.400">
            Wards.lol
          </Text>
        </HStack>
      </MotionHeading>

      <Box mt={4}>
        <Text fontSize="lg" color="gray.300">
          Dive into esports match analysis.
        </Text>
        <Text fontSize="lg" color="gray.300">
          Powered by{" "}
          <ChakraLink
            href="https://grid.gg/get-league-of-legends/"
            isExternal
            color="blue.400"
            fontWeight="semibold"
            _hover={{ color: "blue.300", textDecoration: "underline" }}
          >
            GRID
          </ChakraLink>
        </Text>
      </Box>

      <MotionBox initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
        <Button
          as={RouterLink}
          to="/demo"
          size="lg"
          colorScheme="blue"
          rounded="xl"
          shadow="lg"
        >
          View Demo
        </Button>

        {/* Contact info */}
        <Text mt={4} fontSize="md" color="gray.400">
          Contact us:{" "}
          <ChakraLink
            href="mailto:find@wards.lol"
            color="blue.400"
            fontWeight="medium"
            _hover={{ textDecoration: "underline", color: "blue.300" }}
          >
            find@wards.lol
          </ChakraLink>
        </Text>
      </MotionBox>

      {/* Footer disclaimer (kept on landing page for branding) */}
      <Text fontSize="sm" color="gray.400" pt={10}>
        Disclaimer: This site is not officially affiliated with Riot Games or League of Legends.
      </Text>
    </VStack>
  );
}

function App() {
  return (
    <HelmetProvider>
        <ChakraProvider>
        <Helmet defaultTitle="Wards.lol | Pro LoL Stats" />
          <Router>
            <AssetPreloader />
            <Box
              minH="100vh"
              bg="gray.900"
              color="white"
              display="flex"
              flexDirection="column"
            >
              <Seo
                  title="Game Analysis – Pro LoL Esport Match Insights | Wards.lol"
                  description="Explore pro League of Legends game performance: match stats, warding behaviour, objective control, jungle pathing, gold difference."
                url="https://wards.lol"
              />
              {/* 🔝 Header visible on all pages */}
              <Header />

              {/* 📄 Main content area */}
              <Box flex="1" w="100%">
                <Routes>
                  <Route path="/" element={<Home />} />
                  <Route path="/match/:matchId/game/:gameId" element={<GameViewer />} />
                  <Route path="/match/:matchId" element={<GameViewer />} />

                  <Route path="/team/:slug" element={<TeamPage />} />

                  <Route path="/demo" element={<DemoViewer />} />
                  <Route path="/demo/team" element={<TeamDemoPage />} />
                  <Route path="/demo/player" element={<PlayerDemoPage />} />

                  <Route path="/match_list" element={<MatchList />} />
                  <Route path="/team_list" element={<TeamList />} />

                  <Route path="/draft" element={<DraftLoader />} />
                  <Route path="/draft/:id" element={<DraftLoader />} />

                  <Route path="/blog" element={<BlogList />} />
                  <Route path="/blog/:slug" element={<BlogPost />} />

                </Routes>
              </Box>

              {/* 🔚 Footer always at bottom */}
              <Footer />
            </Box>
          </Router>
        </ChakraProvider>
    </HelmetProvider>
  );
}

export default App;
