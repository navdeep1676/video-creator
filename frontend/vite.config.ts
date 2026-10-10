import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = process.env.VITE_API_PROXY || "http://localhost:8000";
// When Vite is published as localhost:3000 via Docker port map, HMR must use that port
const hmrClientPort = process.env.VITE_HMR_CLIENT_PORT
  ? Number(process.env.VITE_HMR_CLIENT_PORT)
  : undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    // Reliable file watching with Docker Desktop bind mounts (esp. macOS)
    watch: {
      usePolling: process.env.CHOKIDAR_USEPOLLING === "true" || process.env.DOCKER === "true",
      interval: 300,
    },
    hmr: hmrClientPort
      ? {
          clientPort: hmrClientPort,
        }
      : true,
    proxy: {
      "/api": {
        target: apiProxy,
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      "/health": {
        target: apiProxy,
        changeOrigin: true,
      },
    },
  },
});
