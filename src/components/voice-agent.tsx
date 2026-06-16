"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Conversation } from "@11labs/client";
import { Mic, MicOff, PhoneOff, Loader2, AudioLines } from "lucide-react";

interface VoiceAgentProps {
  agentId: string;
}

type Status = "idle" | "connecting" | "connected" | "error";
type Mode = "listening" | "speaking";
type Turn = { role: "user" | "assistant"; content: string };

export function VoiceAgent({ agentId }: VoiceAgentProps) {
  const conversationRef = useRef<Conversation | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const [status, setStatus] = useState<Status>("idle");
  const [mode, setMode] = useState<Mode>("listening");
  const [isMuted, setIsMuted] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [transcript, setTranscript] = useState<Turn[]>([]);

  const isConnected = status === "connected";

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  const startSession = useCallback(async () => {
    if (status === "connecting" || status === "connected") return;
    if (!agentId) {
      setStatus("error");
      setErrorMsg(
        "Falta NEXT_PUBLIC_ELEVENLABS_AGENT_ID. Ejecuta `npm run agent:create`."
      );
      return;
    }

    setStatus("connecting");
    setErrorMsg("");
    setTranscript([]);

    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setStatus("error");
      setErrorMsg(
        "Permiso de micrófono denegado. Actívalo en la configuración del navegador."
      );
      return;
    }

    try {
      const conversation = await Conversation.startSession({
        agentId,
        connectionType: "websocket",
        onConnect: () => setStatus("connected"),
        onDisconnect: (details) => {
          if (details?.reason === "error") {
            setStatus("error");
            setErrorMsg(details.message || "Error de conexión");
          } else {
            setStatus("idle");
          }
          setMode("listening");
          conversationRef.current = null;
        },
        onMessage: ({ message, source }) => {
          setTranscript((prev) => [
            ...prev,
            { role: source === "ai" ? "assistant" : "user", content: message },
          ]);
        },
        onModeChange: ({ mode: m }) => setMode(m as Mode),
        onError: (msg) => {
          setErrorMsg(typeof msg === "string" ? msg : "Error de conexión");
        },
      });

      conversationRef.current = conversation;
    } catch (err) {
      setStatus("error");
      setErrorMsg(
        err instanceof Error ? err.message : "Error al iniciar la sesión de voz"
      );
    }
  }, [agentId, status]);

  const endSession = useCallback(async () => {
    await conversationRef.current?.endSession();
    conversationRef.current = null;
    setStatus("idle");
    setMode("listening");
  }, []);

  const toggleMute = useCallback(() => {
    if (!conversationRef.current) return;
    conversationRef.current.setMicMuted(!isMuted);
    setIsMuted(!isMuted);
  }, [isMuted]);

  useEffect(() => {
    return () => {
      conversationRef.current?.endSession().catch(() => {});
    };
  }, []);

  const orbState: string =
    status === "connecting"
      ? "connecting"
      : status === "error"
        ? "error"
        : isConnected
          ? mode
          : "idle";

  const statusLabel =
    status === "connecting"
      ? "Conectando…"
      : status === "error"
        ? "Error"
        : isConnected
          ? mode === "speaking"
            ? "Hablando…"
            : "Escuchando…"
          : "Toca para hablar";

  return (
    <div className="flex w-full max-w-lg flex-col items-center">
      {/* Orb */}
      <button
        onClick={() => {
          if (status === "idle" || status === "error") startSession();
        }}
        disabled={status === "connecting" || isConnected}
        className={`orb ${orbState} ${
          status === "idle" || status === "error"
            ? "cursor-pointer"
            : "cursor-default"
        }`}
        aria-label="Iniciar conversación de voz"
      >
        <span className="orb-ring" />
        <span className="orb-core" />
        {orbState === "speaking" && (
          <>
            <span className="wave" />
            <span className="wave w2" />
            <span className="wave w3" />
          </>
        )}
        <span className="relative z-10 text-white">
          {status === "connecting" ? (
            <Loader2 className="h-9 w-9 animate-spin" />
          ) : isConnected && mode === "speaking" ? (
            <AudioLines className="h-9 w-9" />
          ) : (
            <Mic className="h-9 w-9" />
          )}
        </span>
      </button>

      {/* Status */}
      <p className="mt-7 text-sm font-medium tracking-wide text-white/70">
        {statusLabel}
      </p>

      {/* Error */}
      {status === "error" && (
        <div className="fade-in mt-3 max-w-sm rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-center text-xs text-red-300">
          {errorMsg}
        </div>
      )}

      {/* Controls */}
      {isConnected && (
        <div className="fade-in mt-6 flex items-center gap-3">
          <button
            onClick={toggleMute}
            className={`rounded-full p-3 transition-all ${
              isMuted
                ? "bg-red-500/20 text-red-300"
                : "bg-white/10 text-white hover:bg-white/20"
            }`}
            title={isMuted ? "Activar micrófono" : "Silenciar"}
          >
            {isMuted ? (
              <MicOff className="h-5 w-5" />
            ) : (
              <Mic className="h-5 w-5" />
            )}
          </button>
          <button
            onClick={endSession}
            className="flex items-center gap-2 rounded-full bg-red-600 px-5 py-3 text-sm font-medium text-white transition-all hover:bg-red-700 active:scale-95"
          >
            <PhoneOff className="h-4 w-4" />
            Finalizar
          </button>
        </div>
      )}

      {/* Transcript */}
      {transcript.length > 0 && (
        <div className="fade-in mt-8 max-h-72 w-full space-y-3 overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-md">
          {transcript.map((t, i) => (
            <div
              key={i}
              className={`flex ${
                t.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <span
                className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                  t.role === "user"
                    ? "bg-[#0a3d91]/60 text-white"
                    : "bg-white/10 text-white/90"
                }`}
              >
                {t.content}
              </span>
            </div>
          ))}
          <div ref={transcriptEndRef} />
        </div>
      )}
    </div>
  );
}
