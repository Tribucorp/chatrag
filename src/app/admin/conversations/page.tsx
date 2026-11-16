"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, BarChart3, Loader2, MessageSquare, RefreshCw } from "lucide-react";

// Vista operativa de conversaciones + consumo del RAG — sobre `ConversationLog` (backend), un
// buffer en memoria siempre activo, DISTINTO del audit trail (`/admin`, tribu-audit): esto se
// pierde al reiniciar el proceso a propósito, es una vista rápida para el admin, no el registro
// de cumplimiento.

type ConversationEntry = {
  timestamp_unix: number;
  user_id: string;
  question: string;
  answer: string;
  abstained: boolean;
  citations_shown: string[];
};

type SourceCount = { source_uri: string; count: number };

type RagMetrics = {
  total_queries: number;
  total_answered: number;
  total_abstained: number;
  abstention_rate: number;
  top_sources: SourceCount[];
};

const TOKEN_KEY = "chatrag-admin-token";

export default function AdminConversationsPage() {
  const [token, setToken] = useState("");
  const [entries, setEntries] = useState<ConversationEntry[] | null>(null);
  const [metrics, setMetrics] = useState<RagMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (tok: string) => {
    setLoading(true);
    setError("");
    try {
      const [convResp, metricsResp] = await Promise.all([
        fetch("/api/admin/conversations?limit=50", {
          headers: { Authorization: `Bearer ${tok}` },
        }),
        fetch("/api/admin/metrics", { headers: { Authorization: `Bearer ${tok}` } }),
      ]);
      if (!convResp.ok) throw new Error(`conversations respondió ${convResp.status}`);
      if (!metricsResp.ok) throw new Error(`metrics respondió ${metricsResp.status}`);
      setEntries(await convResp.json());
      setMetrics(await metricsResp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "error cargando conversaciones");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- token de sessionStorage, ver src/app/admin/page.tsx
      setToken(saved);
      void load(saved);
    }
  }, [load]);

  if (!token) {
    return (
      <main className="mx-auto max-w-xl px-6 py-10 text-sm text-white/50">
        Sin token de admin — entra primero en{" "}
        <Link href="/admin" className="underline">
          /admin
        </Link>
        .
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
          <Link href="/admin" className="text-white/40 hover:text-white/70" aria-label="Volver a admin">
            <ArrowLeft className="h-3.5 w-3.5" />
          </Link>
          <MessageSquare className="h-3.5 w-3.5" />
          ChatRAG · Conversaciones
        </span>
        <button
          onClick={() => load(token)}
          disabled={loading}
          className="flex items-center gap-1 text-xs text-white/50 hover:text-white/80"
        >
          {loading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          refrescar
        </button>
      </header>

      {error && <p className="text-sm text-[#d52b1e]">{error}</p>}

      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <BarChart3 className="h-4 w-4 text-white/40" />
          Consumo del RAG
        </h2>
        {metrics ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-white/70 sm:grid-cols-4">
            <dt className="text-white/40">consultas</dt>
            <dd className="col-span-3">{metrics.total_queries}</dd>
            <dt className="text-white/40">respondidas</dt>
            <dd className="col-span-3">{metrics.total_answered}</dd>
            <dt className="text-white/40">abstenciones</dt>
            <dd className="col-span-3">
              {metrics.total_abstained} ({(metrics.abstention_rate * 100).toFixed(0)}%)
            </dd>
            <dt className="text-white/40">fuentes top</dt>
            <dd className="col-span-3">
              {metrics.top_sources.length > 0 ? (
                <ul className="flex flex-col gap-0.5">
                  {metrics.top_sources.map((s) => (
                    <li key={s.source_uri} className="truncate">
                      {s.source_uri} — {s.count}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-white/30">sin datos todavía</span>
              )}
            </dd>
          </dl>
        ) : (
          <p className="text-xs text-white/40">sin datos todavía</p>
        )}
      </section>

      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <h2 className="mb-3 text-sm font-semibold">Conversaciones recientes</h2>
        {entries && entries.length > 0 ? (
          <ul className="flex flex-col gap-3 text-xs text-white/70">
            {entries.map((e) => (
              <li key={`${e.timestamp_unix}-${e.user_id}`} className="border-b border-white/5 pb-3">
                <div className="mb-1 flex items-center gap-2 text-white/40">
                  <span>{new Date(e.timestamp_unix * 1000).toLocaleString("es-CL")}</span>
                  <span>·</span>
                  <span>{e.user_id}</span>
                  {e.abstained && (
                    <span className="rounded-md border border-[#d52b1e]/40 px-1.5 py-0.5 text-[10px] text-[#d52b1e]">
                      abstención
                    </span>
                  )}
                </div>
                <p className="text-white/90">{e.question}</p>
                <p className="mt-1 text-white/60">{e.answer}</p>
                {e.citations_shown.length > 0 && (
                  <p className="mt-1 text-[11px] text-white/30">
                    fuentes: {e.citations_shown.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-white/40">sin conversaciones todavía</p>
        )}
      </section>
    </main>
  );
}
