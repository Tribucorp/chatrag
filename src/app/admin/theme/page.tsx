"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Palette } from "lucide-react";

import { DEFAULT_THEME, VOICE_STOCK_CATALOG, type Theme } from "@/lib/theme";

const TOKEN_KEY = "chatrag-admin-token";

export default function AdminThemePage() {
  const [token, setToken] = useState("");
  const [theme, setThemeState] = useState<Theme>(DEFAULT_THEME);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (tok: string) => {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/admin/theme", {
        headers: { Authorization: `Bearer ${tok}` },
      });
      if (!resp.ok) throw new Error(`GET /admin/theme respondió ${resp.status}`);
      setThemeState(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "error cargando el tema");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const savedToken = sessionStorage.getItem(TOKEN_KEY);
    if (savedToken) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- token de sessionStorage, ver src/app/admin/page.tsx
      setToken(savedToken);
      void load(savedToken);
    }
  }, [load]);

  const save = useCallback(async () => {
    setLoading(true);
    setSaved(false);
    setError("");
    try {
      const resp = await fetch("/api/admin/theme", {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(theme),
      });
      if (!resp.ok) throw new Error(`PUT /admin/theme respondió ${resp.status}`);
      setThemeState(await resp.json());
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "error guardando el tema");
    } finally {
      setLoading(false);
    }
  }, [token, theme]);

  const field = <K extends keyof Theme>(key: K, value: Theme[K]) =>
    setThemeState((t) => ({ ...t, [key]: value }));

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
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex items-center gap-3">
        <Link href="/admin" className="text-white/40 hover:text-white/70" aria-label="Volver a admin">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
          <Palette className="h-3.5 w-3.5" />
          ChatRAG · Tema
        </div>
      </header>

      {error && <p className="text-sm text-[#d52b1e]">{error}</p>}

      <section className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <h2 className="text-xs font-semibold uppercase tracking-[0.15em] text-white/40">
          Textos de la cabecera
        </h2>
        <label className="flex flex-col gap-1 text-xs text-white/50">
          Etiqueta pequeña (eyebrow)
          <input
            value={theme.eyebrow_text}
            onChange={(e) => field("eyebrow_text", e.target.value)}
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-white/50">
          Título
          <input
            value={theme.heading_text}
            onChange={(e) => field("heading_text", e.target.value)}
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-white/50">
          Descripción
          <textarea
            value={theme.description_text}
            onChange={(e) => field("description_text", e.target.value)}
            rows={4}
            className="resize-y rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
          />
        </label>
      </section>

      <section className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <label className="flex flex-col gap-1 text-xs text-white/50">
          Nombre de la app
          <input
            value={theme.app_name}
            onChange={(e) => field("app_name", e.target.value)}
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-white/50">
          Logo (URL, opcional)
          <input
            value={theme.logo_url ?? ""}
            onChange={(e) => field("logo_url", e.target.value || null)}
            placeholder="https://…"
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
          />
        </label>

        <div className="grid grid-cols-3 gap-3">
          <label className="flex flex-col gap-1 text-xs text-white/50">
            Color primario
            <input
              type="color"
              value={theme.color_accent}
              onChange={(e) => field("color_accent", e.target.value)}
              className="h-9 w-full rounded-lg border border-white/10 bg-white/[0.03]"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-white/50">
            Color secundario
            <input
              type="color"
              value={theme.color_accent_secondary}
              onChange={(e) => field("color_accent_secondary", e.target.value)}
              className="h-9 w-full rounded-lg border border-white/10 bg-white/[0.03]"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-white/50">
            Fondo
            <input
              type="color"
              value={theme.color_background}
              onChange={(e) => field("color_background", e.target.value)}
              className="h-9 w-full rounded-lg border border-white/10 bg-white/[0.03]"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs text-white/50">
          Tipografía (font-family CSS)
          <input
            value={theme.font_family}
            onChange={(e) => field("font_family", e.target.value)}
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs text-white/50">
            Densidad
            <select
              value={theme.density}
              onChange={(e) => field("density", e.target.value as Theme["density"])}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            >
              <option value="comfortable">Cómoda</option>
              <option value="compact">Compacta</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-white/50">
            Burbujas de chat
            <select
              value={theme.bubble_style}
              onChange={(e) => field("bubble_style", e.target.value as Theme["bubble_style"])}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            >
              <option value="rounded">Redondeadas</option>
              <option value="square">Cuadradas</option>
            </select>
          </label>
        </div>

        <div className="flex flex-col gap-1 border-t border-white/10 pt-4">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.15em] text-white/40">
            Voz
          </h2>
          <label className="flex flex-col gap-1 text-xs text-white/50">
            Voz del asistente (catálogo stock de tribu-voice — nunca clonación)
            <select
              value={theme.voice_id}
              onChange={(e) => field("voice_id", e.target.value)}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            >
              {VOICE_STOCK_CATALOG.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs text-white/30">
            Solo aplica si la voz está habilitada (NEXT_PUBLIC_VOICE_ENABLED). El nombre de
            marca de la voz es el mismo &quot;Nombre de la app&quot; de arriba.
          </p>
        </div>

        <button
          onClick={save}
          disabled={loading}
          className="flex items-center justify-center gap-2 rounded-xl bg-[#3b82f6] px-4 py-2 text-sm font-medium disabled:opacity-40"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar tema
        </button>
        {saved && <p className="text-center text-xs text-white/40">Guardado.</p>}
      </section>
    </main>
  );
}
