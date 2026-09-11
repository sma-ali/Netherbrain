import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server in .next/standalone: the Docker image needs no npm install.
  output: "standalone",
};

export default nextConfig;
