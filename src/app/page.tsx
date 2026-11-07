"use client";

import { ChatAgent } from "@/components/chat-agent";
import { useTheme } from "@/lib/theme-context";

export default function Home() {
  const theme = useTheme();

  return (
    <main className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 py-10">
      <header className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
        {theme.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- logo remoto configurable en runtime, no puede pasar por next/image (dominio no conocido en build)
          <img src={theme.logo_url} alt="" className="h-4 w-4 rounded-full object-cover" />
        ) : (
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: "var(--chatrag-accent-secondary)" }}
          />
        )}
        {theme.eyebrow_text}
      </header>
      <h1 className="mb-3 text-center text-4xl font-semibold tracking-tight sm:text-5xl">
        <span className="bg-gradient-to-r from-[var(--chatrag-accent)] via-white to-[var(--chatrag-accent-secondary)] bg-clip-text text-transparent">
          {theme.heading_text}
        </span>
      </h1>
      <p className="mb-10 max-w-md text-center text-sm leading-relaxed text-white/55">
        {theme.description_text}
      </p>

      <ChatAgent />

      <footer className="mt-12 text-center text-[11px] text-white/35">
        RAG sobre munistgo.cl · Tribu SDK (on-prem, NVIDIA-native)
      </footer>
    </main>
  );
}
