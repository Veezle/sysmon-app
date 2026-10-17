import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build jde do sysmon_app/web/ a assety pod static/assets/, takze je serviruje
// dnesni demon beze zmeny kontraktu: GET / a GET /static/*.
// Dev server proxyuje /stats a /events na beziciho demona (8430), aby se
// nemuselo po kazde zmene buildit.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../sysmon_app/web",
    emptyOutDir: true,
    assetsDir: "static/assets",
    sourcemap: false,
  },
  server: {
    proxy: {
      "/stats": "http://127.0.0.1:8430",
      "/events": "http://127.0.0.1:8430",
    },
  },
});
