"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, UserPlus, Loader2 } from "lucide-react";
import { signIn, signUp } from "@/lib/auth-client";

export default function LoginPage() {
  const router = useRouter();
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
        <span className="inline-block h-2 w-2 rounded-full bg-[#d52b1e]" />
        Ilustre Municipalidad de Santiago
      </header>
      <h1 className="mb-8 text-center text-3xl font-semibold tracking-tight sm:text-4xl">
        {mode === "sign-in" ? "Iniciar sesión" : "Crear cuenta"}
      </h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex w-full max-w-sm flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      >
        {mode === "sign-up" && (
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre"
            className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-white/25"
          />
        )}
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Correo"
          required
          className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-white/25"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña"
          required
          minLength={8}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm outline-none focus:border-white/25"
        />

        {error && <p className="text-center text-xs text-[#d52b1e]">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 flex h-11 items-center justify-center gap-2 rounded-xl bg-[#3b82f6] text-sm font-medium disabled:opacity-40"
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

      <p className="mt-6 max-w-sm text-center text-[11px] text-white/35">
        Demo: admin@munistgo.cl / rrhh@munistgo.cl / finanzas@munistgo.cl / vecino@munistgo.cl —
        contraseña <code className="text-white/50">vecino-demo-2026</code>
      </p>
    </main>
  );
}
