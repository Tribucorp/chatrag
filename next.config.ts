import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Evita que Next infiera un workspace root erróneo por lockfiles en carpetas padre. Se amplía
  // al padre común con tribu-sdk (prueba: @tribu/auth es un symlink `file:` fuera de este repo).
  turbopack: { root: path.resolve(__dirname, "..") },
};

export default nextConfig;
