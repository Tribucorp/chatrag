import { DEMO_PASSWORD, DEMO_SEED_ENABLED } from "@/lib/seed-demo";

import { LoginForm } from "./login-form";

// Server Component: decide en el servidor si se muestran las credenciales demo (solo con
// CHATRAG_AUTH_DEMO_SEED=1, que es cuando existen de verdad).
export default function LoginPage() {
  return <LoginForm demoPassword={DEMO_SEED_ENABLED ? DEMO_PASSWORD : null} />;
}
