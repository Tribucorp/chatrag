import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Evita que Next infiera un workspace root erróneo por lockfiles en carpetas padre.
  turbopack: { root: __dirname },
};

export default nextConfig;
