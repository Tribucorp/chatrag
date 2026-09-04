import { ChatAgent } from "@/components/chat-agent";

export default function Home() {
  return (
    <main className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 py-10">
      <header className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
        <span className="inline-block h-2 w-2 rounded-full bg-[#d52b1e]" />
        Ilustre Municipalidad de Santiago
      </header>
      <h1 className="mb-3 text-center text-4xl font-semibold tracking-tight sm:text-5xl">
        Asistente de la{" "}
        <span className="bg-gradient-to-r from-[#3b82f6] via-white to-[#d52b1e] bg-clip-text text-transparent">
          comuna de Santiago
        </span>
      </h1>
      <p className="mb-10 max-w-md text-center text-sm leading-relaxed text-white/55">
        Asistente oficial de la comuna de Santiago de Chile. Consúltame sobre
        trámites y servicios municipales, direcciones del municipio, el alcalde
        Mario Desbordes o cualquier información del sitio munistgo.cl. Escribe tu
        pregunta y te respondo con el enlace directo del trámite y su fuente.
      </p>

      <ChatAgent />

      <footer className="mt-12 text-center text-[11px] text-white/35">
        RAG sobre munistgo.cl · Tribu SDK (on-prem, NVIDIA-native)
      </footer>
    </main>
  );
}
