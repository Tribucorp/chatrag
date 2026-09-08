"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Send, Loader2, ShieldCheck, MicOff, LogOut } from "lucide-react";
import { signOut } from "@/lib/auth-client";

// Reemplaza al antiguo VoiceAgent acoplado a ElevenLabs (proveedor cloud, incompatible con la
// constitución on-prem del Tribu SDK). Ahora consulta al BFF del propio frontend (`/api/chat`),
// que valida la sesión real (tribu-auth) y reenvía al backend RAG del SDK con identidad —
// el navegador ya NO llama al backend directamente ni conoce su URL. Las respuestas llegan con
// CITAS VERIFICABLES ya filtradas por ACL en el servidor. La voz queda como stub apagado hasta
// que se levante el bloqueo legal de tribu-voice (Riva stock, jamás clonación).

type Citation = { text: string; source_uri: string; title: string; score: number };
type Answer = { text: string; citations: Citation[]; abstained: boolean };
type Turn = { role: "user" | "assistant"; content: string; citations?: Citation[] };

const VOICE_ENABLED = process.env.NEXT_PUBLIC_VOICE_ENABLED === "1";

export function ChatAgent() {
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const logout = useCallback(async () => {
    await signOut();
    router.push("/login");
    router.refresh();
  }, [router]);

  const send = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    setError("");
    setTurns((t) => [...t, { role: "user", content: question }]);
    setLoading(true);
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!resp.ok) throw new Error(`El backend respondió ${resp.status}`);
      const answer: Answer = await resp.json();
      setTurns((t) => [
        ...t,
        { role: "assistant", content: answer.text, citations: answer.citations },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error consultando el asistente");
    } finally {
      setLoading(false);
    }
  }, [input, loading]);

  return (
    <div className="flex w-full max-w-xl flex-col gap-4">
      <div className="flex items-center justify-center gap-3 text-[11px] text-white/40">
        <span className="flex items-center gap-2">
          <ShieldCheck className="h-3.5 w-3.5" />
          Respuestas con citas verificables · RAG on-prem (Tribu SDK)
        </span>
        <button
          onClick={logout}
          className="flex items-center gap-1 underline decoration-white/20 hover:text-white/70"
        >
          <LogOut className="h-3 w-3" />
          Salir
        </button>
      </div>

      <div className="min-h-[240px] rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        {turns.length === 0 ? (
          <p className="py-16 text-center text-sm text-white/40">
            Escribe tu consulta sobre trámites y servicios municipales.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {turns.map((turn, i) => (
              <li key={i} className={turn.role === "user" ? "text-right" : "text-left"}>
                <div
                  className={
                    turn.role === "user"
                      ? "inline-block rounded-2xl bg-[#3b82f6]/20 px-4 py-2 text-sm"
                      : "inline-block rounded-2xl bg-white/[0.06] px-4 py-2 text-sm"
                  }
                >
                  {turn.content}
                </div>
                {turn.citations && turn.citations.length > 0 && (
                  <ul className="mt-2 flex flex-col gap-1 text-left">
                    {turn.citations.map((c, j) => (
                      <li key={j} className="text-[11px] text-white/45">
                        <a
                          href={c.source_uri}
                          className="underline decoration-white/20 hover:text-white/70"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {c.title || c.source_uri}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
            <div ref={endRef} />
          </ul>
        )}
      </div>

      {error && <p className="text-center text-xs text-[#d52b1e]">{error}</p>}

      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Escribe tu pregunta…"
          className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-white/25"
        />
        <button
          onClick={send}
          disabled={loading}
          className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#3b82f6] disabled:opacity-40"
          aria-label="Enviar"
        >
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
        </button>
      </div>

      {!VOICE_ENABLED && (
        <div className="flex items-center justify-center gap-2 text-[11px] text-white/35">
          <MicOff className="h-3.5 w-3.5" />
          Voz deshabilitada (tribu-voice pendiente de aprobación legal — Riva stock, sin clonación)
        </div>
      )}
    </div>
  );
}
