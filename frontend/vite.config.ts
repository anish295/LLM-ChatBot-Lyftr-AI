import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
