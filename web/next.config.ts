import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // образ сервера (E9): node server.js без node_modules
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
