"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  FileUp,
  KeyRound,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

// Panel de administración de ChatRAG: estado del índice RAG, reindexado bajo demanda, y traza
// de auditoría. El navegador nunca conoce CHATRAG_API_URL (proxy en
// src/app/api/admin/[...path]/route.ts) ni tiene el bearer de admin guardado en ningún sitio
// persistente — se escribe en cada sesión de pestaña (sessionStorage), no en localStorage ni en
// una cookie, para que no sobreviva más de lo necesario.

type IndexStatus = {
  tenant_id: string;
  milvus_uri: string;
  embed_dim: number;
  nim_embed_model_id: string;
  nim_rerank_model_id: string;
  knowledge_dir: string;
  source_files: string[];
};

type IngestReport = { document_id: string; chunks: number };

type AuditEntry = {
  entry_id: string;
  actor_id: string;
  action: string;
  payload: Record<string, unknown>;
  recorded_at_unix: number;
};

const TOKEN_KEY = "chatrag-admin-token";

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [tokenSaved, setTokenSaved] = useState(false);
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [reports, setReports] = useState<IngestReport[] | null>(null);
  const [audit, setAudit] = useState<AuditEntry[] | "no-configurado" | null>(null);
  const [loading, setLoading] = useState<"status" | "reindex" | "audit" | "upload" | null>(
    null
  );
  const [error, setError] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [uploadText, setUploadText] = useState("");
  const [uploadOk, setUploadOk] = useState<IngestReport | null>(null);

  // `tok` explícito en vez de leer el estado `token` por closure: el efecto de montaje
  // restaura el token de sessionStorage y dispara la carga inicial en el mismo tick, antes de
  // que el re-render que actualizaría el closure de `token` ocurra — pasarlo como argumento
  // evita depender de un valor de estado todavía no confirmado.
  const loadStatus = useCallback(async (tok: string) => {
    setLoading("status");
    setError("");
    try {
      const resp = await fetch("/api/admin/index-status", {
        headers: { Authorization: `Bearer ${tok}` },
      });
      if (!resp.ok) throw new Error(`index-status respondió ${resp.status}`);
      setStatus(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "error consultando el estado del índice");
    } finally {
      setLoading(null);
    }
  }, []);

  const loadAudit = useCallback(async (tok: string) => {
    setLoading("audit");
    try {
      const resp = await fetch("/api/admin/audit", {
        headers: { Authorization: `Bearer ${tok}` },
      });
      if (resp.status === 503) {
        setAudit("no-configurado");
        return;
      }
      if (!resp.ok) throw new Error(`audit respondió ${resp.status}`);
      setAudit(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "error consultando la auditoría");
    } finally {
      setLoading(null);
    }
  }, []);

  useEffect(() => {
    // sessionStorage es por-pestaña y solo existe en el navegador — no se puede leer durante
    // el render (SSR) ni con un inicializador perezoso de useState sin arriesgar un mismatch
    // de hidratación, así que el patrón aceptado es leerlo una vez al montar.
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- ver comentario arriba
      setToken(saved);
      setTokenSaved(true);
      void loadStatus(saved);
      void loadAudit(saved);
    }
  }, [loadStatus, loadAudit]);

  const saveToken = useCallback(() => {
    sessionStorage.setItem(TOKEN_KEY, token);
    setTokenSaved(true);
    void loadStatus(token);
    void loadAudit(token);
  }, [token, loadStatus, loadAudit]);

  const reindex = useCallback(async () => {
    setLoading("reindex");
    setError("");
    setReports(null);
    try {
      const resp = await fetch("/api/admin/reindex", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`reindex respondió ${resp.status}`);
      setReports(await resp.json());
      void loadStatus(token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "error reindexando");
    } finally {
      setLoading(null);
    }
  }, [token, loadStatus]);

  const uploadSource = useCallback(async () => {
    const documentId = uploadName.trim().endsWith(".md")
      ? uploadName.trim()
      : `${uploadName.trim()}.md`;
    if (!uploadName.trim() || !uploadText.trim()) return;
    setLoading("upload");
    setError("");
    setUploadOk(null);
    try {
      const resp = await fetch("/api/admin/sources", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: documentId, text: uploadText }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        throw new Error(body?.detail ? String(body.detail) : `sources respondió ${resp.status}`);
      }
      setUploadOk(await resp.json());
      setUploadName("");
      setUploadText("");
      void loadStatus(token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "error subiendo el documento");
    } finally {
      setLoading(null);
    }
  }, [token, uploadName, uploadText, loadStatus]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
          <Link href="/" className="text-white/40 hover:text-white/70" aria-label="Volver al chat">
            <ArrowLeft className="h-3.5 w-3.5" />
          </Link>
          <ShieldCheck className="h-3.5 w-3.5" />
          ChatRAG · Admin
        </span>
        <div className="flex items-center gap-4">
          <Link
            href="/admin/conversations"
            className="text-xs font-medium normal-case tracking-normal text-white/40 hover:text-white/70"
          >
            Conversaciones →
          </Link>
          <Link
            href="/admin/theme"
            className="text-xs font-medium normal-case tracking-normal text-white/40 hover:text-white/70"
          >
            Editar tema →
          </Link>
        </div>
      </header>

      <section className="flex items-center gap-2">
        <KeyRound className="h-4 w-4 text-white/40" />
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Bearer de admin (CHATRAG_ADMIN_TOKEN)"
          className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 text-sm outline-none focus:border-white/25"
        />
        <button
          onClick={saveToken}
          disabled={!token}
          className="rounded-xl bg-[#3b82f6] px-4 py-2 text-sm font-medium disabled:opacity-40"
        >
          Entrar
        </button>
      </section>

      {error && <p className="text-sm text-[#d52b1e]">{error}</p>}

      {tokenSaved && (
        <>
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Estado del índice</h2>
              <button
                onClick={() => loadStatus(token)}
                disabled={loading === "status"}
                className="flex items-center gap-1 text-xs text-white/50 hover:text-white/80"
              >
                {loading === "status" ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <RefreshCw className="h-3 w-3" />
                )}
                refrescar
              </button>
            </div>
            {status ? (
              <div className="flex flex-col gap-3">
                <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-white/70 sm:grid-cols-2">
                  <dt className="text-white/40">tenant</dt>
                  <dd className="truncate">{status.tenant_id}</dd>
                  <dt className="text-white/40">milvus</dt>
                  <dd className="truncate">{status.milvus_uri}</dd>
                  <dt className="text-white/40">embed_dim</dt>
                  <dd>{status.embed_dim}</dd>
                  <dt className="text-white/40">modelo embed</dt>
                  <dd className="truncate">{status.nim_embed_model_id}</dd>
                  <dt className="text-white/40">modelo rerank</dt>
                  <dd className="truncate">{status.nim_rerank_model_id}</dd>
                  <dt className="text-white/40">knowledge_dir</dt>
                  <dd className="truncate">{status.knowledge_dir}</dd>
                </dl>
                <div>
                  <p className="mb-1 text-xs text-white/40">
                    fuentes ({status.source_files.length})
                  </p>
                  {status.source_files.length > 0 ? (
                    <ul className="flex flex-wrap gap-1.5">
                      {status.source_files.map((f) => (
                        <li
                          key={f}
                          className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-white/60"
                        >
                          {f}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-white/30">sin fuentes todavía</p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-white/40">sin datos todavía</p>
            )}
          </section>

          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <h2 className="mb-3 text-sm font-semibold">Subir documento</h2>
            <div className="flex flex-col gap-2">
              <input
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder="nombre-del-documento (se le agrega .md)"
                className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
              />
              <textarea
                value={uploadText}
                onChange={(e) => setUploadText(e.target.value)}
                placeholder="Contenido en Markdown…"
                rows={5}
                className="resize-y rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
              />
              <button
                onClick={uploadSource}
                disabled={loading === "upload" || !uploadName.trim() || !uploadText.trim()}
                className="flex items-center justify-center gap-2 self-start rounded-lg bg-[#3b82f6] px-3 py-1.5 text-xs font-medium disabled:opacity-40"
              >
                {loading === "upload" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileUp className="h-3.5 w-3.5" />
                )}
                subir e ingestar
              </button>
              {uploadOk && (
                <p className="text-xs text-white/40">
                  {uploadOk.document_id} ingestado — {uploadOk.chunks} chunks
                </p>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Reindexar</h2>
              <button
                onClick={reindex}
                disabled={loading === "reindex"}
                className="rounded-lg bg-[#3b82f6] px-3 py-1.5 text-xs font-medium disabled:opacity-40"
              >
                {loading === "reindex" ? "reindexando…" : "reindexar knowledge/"}
              </button>
            </div>
            {reports && (
              <ul className="flex flex-col gap-1 text-xs text-white/70">
                {reports.map((r) => (
                  <li key={r.document_id}>
                    {r.document_id} — {r.chunks} chunks
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <h2 className="mb-3 text-sm font-semibold">Auditoría reciente</h2>
            {audit === "no-configurado" && (
              <p className="text-xs text-white/40">
                auditoría no configurada (CHATRAG_AUDIT_DATABASE_URL/CHATRAG_AUDIT_CHAIN_KEY)
              </p>
            )}
            {audit && audit !== "no-configurado" && (
              <ul className="flex flex-col gap-2 text-xs text-white/70">
                {audit.map((e) => (
                  <li key={e.entry_id} className="border-b border-white/5 pb-2">
                    <span className="text-white/40">{e.actor_id}</span> · {e.action}
                  </li>
                ))}
                {audit.length === 0 && <li className="text-white/40">sin entradas todavía</li>}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
