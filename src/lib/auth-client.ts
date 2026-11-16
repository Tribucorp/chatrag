"use client";

import { createAuthClient } from "better-auth/react";

// Sin baseURL: mismo origen (`/api/auth/*`), donde vive `src/app/api/auth/[...all]/route.ts`.
export const authClient = createAuthClient();

export const { signIn, signUp, signOut } = authClient;
