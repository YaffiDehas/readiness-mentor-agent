import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` proxies /api to the Python bridge (python -m agent.server). The Origin header is rewritten so the
// bridge's same-origin check passes. Production: `npm run build`, then the bridge serves ui/dist itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8787", changeOrigin: true, headers: { Origin: "http://127.0.0.1:8787" } } },
  },
  build: { outDir: "dist", sourcemap: false },
});
