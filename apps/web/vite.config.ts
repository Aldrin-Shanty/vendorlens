import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ mode }) => {
  // Read shared backend credentials only inside the Node-side proxy config.
  // Do not set envPrefix to an empty string: secrets must stay out of the client.
  const rootDir = fileURLToPath(new URL("../../", import.meta.url));
  const webDir = fileURLToPath(new URL("./", import.meta.url));
  const env = {
    ...loadEnv(mode, rootDir, ""),
    ...loadEnv(mode, webDir, ""),
  };
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      proxy: {
        "/api": {
          target: env.API_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
          ...(env.API_KEY ? { headers: { "X-API-Key": env.API_KEY } } : {}),
        },
      },
    },
  };
});
