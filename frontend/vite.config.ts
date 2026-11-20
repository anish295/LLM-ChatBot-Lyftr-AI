import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Optional same-origin API proxy for static hosts (Netlify).
 * When BACKEND_PROXY_TARGET is set at build time, dist/_redirects proxies
 * /api/* to the backend, so the browser only ever talks to the frontend's own
 * origin: no CORS, and no third-party request for privacy extensions to block.
 * Build with VITE_API_BASE_URL=/api in that case.
 */
function netlifyApiProxy(): Plugin {
  return {
    name: "netlify-api-proxy",
    apply: "build",
    closeBundle() {
      const target = (process.env.BACKEND_PROXY_TARGET ?? "").trim().replace(/\/+$/, "");
      if (!target) return;
      const rules = [`/api/*  ${target}/:splat  200!`, `/*  /index.html  200`].join("\n") + "\n";
      fs.writeFileSync(path.resolve(__dirname, "dist/_redirects"), rules);
      console.log(`netlify-api-proxy: /api/* -> ${target}`);
    },
  };
}

export default defineConfig({
  plugins: [react(), netlifyApiProxy()],
  server: { port: 5173, host: true },
  preview: { port: 3000, host: true },
  build: {
    rollupOptions: {
      output: {
        // Keep React and the markdown/highlighting stack in separate, long-cacheable chunks.
        manualChunks: {
          react: ["react", "react-dom"],
          markdown: ["react-markdown", "remark-gfm", "rehype-highlight"],
        },
      },
    },
  },
});
