"use client";

import { createAuthClient } from "better-auth/react";

// Sin baseURL explícita: better-auth/react asume el mismo origen (`/api/auth/*`), que es
// exactamente donde vive el route handler de `src/app/api/auth/[...all]/route.ts`.
export const authClient = createAuthClient();

export const { useSession, signIn, signUp, signOut } = authClient;
