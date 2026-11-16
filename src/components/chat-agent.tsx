"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Send, Loader2, ShieldCheck, Mic, MicOff, Square, LogOut } from "lucide-react";

import { signOut } from "@/lib/auth-client";

// Reemplaza al antiguo VoiceAgent acoplado a ElevenLabs (proveedor cloud, incompatible con la
// constitución on-prem del Tribu SDK). Consulta al BFF (`/api/chat`, ver
// src/app/api/chat/route.ts), que valida la sesión de tribu-auth y reenvía al backend RAG del
// SDK (`/query`) con la identidad y el bearer de servicio — el navegador nunca habla directo con el backend ni
// declara su propia identidad. Las respuestas llegan con CITAS VERIFICABLES ya filtradas por
// ACL en el servidor.
//
// Voz (Fase C, sobre tribu-voice real — ver backend/src/chatrag_api/voice.py): gateada por
// NEXT_PUBLIC_VOICE_ENABLED. El micrófono graba con MediaRecorder, se transcribe vía
// /api/voice/transcribe (ASR propio de ChatRAG, no parte de tribu-voice) y el texto entra al
// mismo flujo que si se hubiera escrito; la respuesta se lee en voz alta vía /api/voice/speak
// (TTS real sobre tribu-voice, solo voces stock). El contrato de red con el NIM Riva real está
// sin verificar (ver docstring de voice.py) — si /api/voice/speak o /transcribe fallan, el chat
// de texto sigue funcionando igual, la voz nunca bloquea la conversación.

type Citation = { text: string; source_uri: string; title: string; score: number };
type Answer = { text: string; citations: Citation[]; abstained: boolean };
type Turn = { role: "user" | "assistant"; content: string; citations?: Citation[] };
type VoiceSession = { token_id: string; face_id: string; expires_at: number };

const VOICE_ENABLED = process.env.NEXT_PUBLIC_VOICE_ENABLED === "1";

export function ChatAgent() {
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const logout = useCallback(async () => {
    await signOut();
    router.push("/login");
    router.refresh();
  }, [router]);

  const speak = useCallback(async (token: VoiceSession, text: string) => {
    try {
      const resp = await fetch("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_id: token.token_id, text, emotion: "neutral" }),
      });
      if (!resp.ok || !audioRef.current) return;
      const blob = await resp.blob();
      audioRef.current.src = URL.createObjectURL(blob);
      await audioRef.current.play();
    } catch {
      // La voz nunca bloquea el chat de texto — un fallo de TTS se ignora en silencio.
    }
  }, []);

  const send = useCallback(
    async (questionOverride?: string, voiceToken?: VoiceSession) => {
      const question = (questionOverride ?? input).trim();
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
        if (resp.status === 401) {
          // Sesión caducada o cerrada en otra pestaña: volver al login en vez de un error.
          router.push("/login");
          return;
        }
        if (!resp.ok) throw new Error(`El backend respondió ${resp.status}`);
        const answer: Answer = await resp.json();
        setTurns((t) => [
          ...t,
          { role: "assistant", content: answer.text, citations: answer.citations },
        ]);
        if (VOICE_ENABLED && voiceToken) void speak(voiceToken, answer.text);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error consultando el asistente");
      } finally {
        setLoading(false);
      }
    },
    [input, loading, speak, router]
  );

  const startRecording = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setError("No se pudo acceder al micrófono.");
    }
  }, []);

  const stopRecording = useCallback(() => {
    setRecording(false);
    setTranscribing(true);
    const recorder = mediaRecorderRef.current;
    if (!recorder) {
      setTranscribing(false);
      return;
    }
    recorder.addEventListener(
      "stop",
      () => {
        void (async () => {
          try {
            const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
            const sessionResp = await fetch("/api/voice/session", { method: "POST" });
            if (!sessionResp.ok) throw new Error("no se pudo abrir sesión de voz");
            const voiceToken: VoiceSession = await sessionResp.json();

            const transcribeResp = await fetch("/api/voice/transcribe", {
              method: "POST",
              headers: { "Content-Type": blob.type, "X-Voice-Token": voiceToken.token_id },
              body: blob,
            });
            if (!transcribeResp.ok) throw new Error("no se pudo transcribir el audio");
            const { text } = (await transcribeResp.json()) as { text: string };
            await send(text, voiceToken);
          } catch (e) {
            setError(e instanceof Error ? e.message : "Error procesando el audio");
          } finally {
            setTranscribing(false);
          }
        })();
      },
      { once: true }
    );
    recorder.stop();
  }, [send]);

  return (
    <div
      className="flex w-full max-w-xl flex-col"
      style={{ gap: "var(--chatrag-gap)" }}
    >
      <div className="flex items-center justify-center gap-3 text-[11px] text-white/40">
        <span className="flex items-center gap-2">
          <ShieldCheck className="h-3.5 w-3.5" />
          Respuestas con citas verificables · RAG on-prem (Tribu SDK)
        </span>
        <button
          type="button"
          onClick={() => void logout()}
          className="flex items-center gap-1 underline decoration-white/20 hover:text-white/70"
        >
          <LogOut className="h-3 w-3" />
          Salir
        </button>
      </div>

      <div
        className="min-h-[240px] rounded-[var(--chatrag-radius)] border border-white/10 bg-white/[0.03]"
        style={{ padding: "var(--chatrag-padding)" }}
      >
        {turns.length === 0 ? (
          <p className="py-16 text-center text-sm text-white/40">
            Escribe tu consulta sobre trámites y servicios municipales.
          </p>
        ) : (
          <ul className="flex flex-col" style={{ gap: "var(--chatrag-gap)" }}>
            {turns.map((turn, i) => (
              <li key={i} className={turn.role === "user" ? "text-right" : "text-left"}>
                <div
                  className={
                    turn.role === "user"
                      ? "inline-block rounded-[var(--chatrag-radius)] px-4 py-2 text-sm"
                      : "inline-block rounded-[var(--chatrag-radius)] bg-white/[0.06] px-4 py-2 text-sm"
                  }
                  style={
                    turn.role === "user"
                      ? {
                          backgroundColor:
                            "color-mix(in srgb, var(--chatrag-accent) 20%, transparent)",
                        }
                      : undefined
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

      {error && (
        <p className="text-center text-xs" style={{ color: "var(--chatrag-accent-secondary)" }}>
          {error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Escribe tu pregunta…"
          className="flex-1 rounded-[var(--chatrag-radius)] border border-white/10 bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-white/25"
        />
        {VOICE_ENABLED && (
          <button
            onClick={recording ? stopRecording : startRecording}
            disabled={transcribing || loading}
            className="flex h-11 w-11 items-center justify-center rounded-[var(--chatrag-radius)] border border-white/10 bg-white/[0.03] disabled:opacity-40"
            style={recording ? { borderColor: "var(--chatrag-accent-secondary)" } : undefined}
            aria-label={recording ? "Detener grabación" : "Grabar pregunta por voz"}
          >
            {transcribing ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : recording ? (
              <Square className="h-4 w-4" style={{ color: "var(--chatrag-accent-secondary)" }} />
            ) : (
              <Mic className="h-5 w-5" />
            )}
          </button>
        )}
        <button
          onClick={() => send()}
          disabled={loading}
          className="flex h-11 w-11 items-center justify-center rounded-[var(--chatrag-radius)] disabled:opacity-40"
          style={{ backgroundColor: "var(--chatrag-accent)" }}
          aria-label="Enviar"
        >
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
        </button>
      </div>

      {VOICE_ENABLED ? (
        <audio ref={audioRef} hidden />
      ) : (
        <div className="flex items-center justify-center gap-2 text-[11px] text-white/35">
          <MicOff className="h-3.5 w-3.5" />
          Voz deshabilitada (NEXT_PUBLIC_VOICE_ENABLED=0) — Riva stock, sin clonación
        </div>
      )}
    </div>
  );
}
