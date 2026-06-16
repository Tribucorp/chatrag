import { VoiceAgent } from "@/components/voice-agent";

export default function Home() {
  const agentId = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID ?? "";

  return (
    <main className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 py-10">
      <header className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
        <span className="inline-block h-2 w-2 rounded-full bg-[#d52b1e]" />
        Asistente de Voz
      </header>
      <h1 className="mb-3 text-center text-4xl font-semibold tracking-tight sm:text-5xl">
        Conversa sobre{" "}
        <span className="bg-gradient-to-r from-[#3b82f6] via-white to-[#d52b1e] bg-clip-text text-transparent">
          Chile
        </span>
      </h1>
      <p className="mb-10 max-w-md text-center text-sm leading-relaxed text-white/55">
        Habla con un agente de voz conversacional sobre geografía, historia,
        cultura, economía y curiosidades del país. Pulsa el orbe y empieza a
        hablar.
      </p>

      <VoiceAgent agentId={agentId} />

      <footer className="mt-12 text-center text-[11px] text-white/35">
        RAG + Agente · ElevenLabs Conversational AI
      </footer>
    </main>
  );
}
