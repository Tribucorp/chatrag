import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Evita que Next infiera un workspace root erróneo por lockfiles en carpetas padre.
  turbopack: { root: __dirname },
  // Imagen Docker de producción (deploy/Dockerfile.frontend, Fase D): standalone copia solo
  // el server.js + node_modules mínimo que Next resuelve por trazado, no todo node_modules/.
  output: "standalone",
};

export default nextConfig;
