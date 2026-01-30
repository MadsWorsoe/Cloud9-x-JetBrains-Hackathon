//main.jsx
import React, { StrictMode } from "react";
import { createRoot } from 'react-dom/client';
import { ChakraProvider, extendTheme, ColorModeScript } from "@chakra-ui/react";
import App from './App.jsx';
import './index.css';

//import "../demo/styles/_globals.css";

const theme = extendTheme({
  config: {
    initialColorMode: "dark", // start in dark mode
    useSystemColorMode: false, // ignore system preference
  },
  styles: {
    global: {
      "html, body": {
        bg: "gray.900",        // default background for all pages
        color: "white",        // default text color
      },
      a: {
        color: "teal.300",     // links
        _hover: { color: "teal.500" },
      },
    },
  },
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ColorModeScript initialColorMode={theme.config.initialColorMode} />
      <ChakraProvider theme={theme}>
        <App />
      </ChakraProvider>
  </StrictMode>
)
