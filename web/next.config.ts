import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // self-contained server bundle for Docker / App Platform
};

export default nextConfig;
