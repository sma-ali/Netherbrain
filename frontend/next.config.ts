import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Génère un serveur autonome dans .next/standalone : l'image Docker n'a pas besoin de npm install.
  output: "standalone",
};

export default nextConfig;
