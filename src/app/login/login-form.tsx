"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, UserPlus, Loader2 } from "lucide-react";

import { signIn, signUp } from "@/lib/auth-client";
import { useTheme } from "@/lib/theme-context";

const INPUT_CLASS =
  "rounded-[var(--chatrag-radius)] border border-white/10 bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-white/25";

export function LoginForm({
  demo,
}: {
  demo: { accounts: readonly string[]; password: string } | null;
}) {
  const router = useRouter();
  const theme = useTheme();
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = useCallback(async () => {
    setLoading(true);
    setError("");
    const result =
      mode === "sign-in"
        ? await signIn.email({ email, password })
        : await signUp.email({ email, password, name: name || email });
    setLoading(false);
    if (result.error) {
      setError(result.error.message ?? "No se pudo iniciar sesión");
      return;
    }
    router.push("/");
    router.refresh();
  }, [mode, email, password, name, router]);

  return (
    <main className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 py-10">
      <header className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-white/50">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: "var(--chatrag-accent-secondary)" }}
        />
        {theme.eyebrow_text}
      </header>
      <h1 className="mb-8 text-center text-3xl font-semibold tracking-tight sm:text-4xl">
        {mode === "sign-in" ? "Iniciar sesión" : "Crear cuenta"}
      </h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        className="flex w-full max-w-sm flex-col gap-3 rounded-[var(--chatrag-radius)] border border-white/10 bg-white/[0.03] p-6"
      >
        {mode === "sign-up" && (
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre"
            aria-label="Nombre"
            className={INPUT_CLASS}
          />
        )}
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Correo"
          aria-label="Correo"
          autoComplete="email"
          required
          className={INPUT_CLASS}
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña"
          aria-label="Contraseña"
          autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          required
          minLength={8}
          className={INPUT_CLASS}
        />

        {error && (
          <p role="alert" className="text-center text-xs text-[var(--chatrag-accent-secondary)]">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 flex h-11 items-center justify-center gap-2 rounded-[var(--chatrag-radius)] bg-[var(--chatrag-accent)] text-sm font-medium disabled:opacity-40"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : mode === "sign-in" ? (
            <LogIn className="h-4 w-4" />
          ) : (
            <UserPlus className="h-4 w-4" />
          )}
          {mode === "sign-in" ? "Entrar" : "Registrarme"}
        </button>

        <button
          type="button"
          onClick={() => setMode(mode === "sign-in" ? "sign-up" : "sign-in")}
          className="text-center text-[11px] text-white/45 underline decoration-white/20 hover:text-white/70"
        >
          {mode === "sign-in" ? "¿No tienes cuenta? Regístrate" : "¿Ya tienes cuenta? Inicia sesión"}
        </button>
      </form>

      {demo && (
        <p className="mt-6 max-w-sm text-center text-[11px] text-white/35">
          Demo: {demo.accounts.join(" / ")} — contraseña{" "}
          <code className="text-white/50">{demo.password}</code>
        </p>
      )}
    </main>
  );
}
