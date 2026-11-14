/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { host: "::", port: 8080 },
  test: { environment: "node", include: ["src/__tests__/**/*.test.ts"], setupFiles: ["src/__tests__/setup.ts"] },
});
