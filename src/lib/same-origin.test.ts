import { describe, expect, it } from "vitest";
import { isSameOrigin } from "./same-origin";

const req = (headers: Record<string, string>) =>
  new Request("http://cualquiera/api/auth/sign-in/email", { method: "POST", headers });

describe("isSameOrigin", () => {
  it("acepta el mismo host (IP de la red del cliente, con puerto)", () => {
    expect(isSameOrigin(req({ host: "192.168.1.20:3000", origin: "http://192.168.1.20:3000" }))).toBe(true);
    expect(isSameOrigin(req({ host: "soporte.cliente.local", origin: "https://soporte.cliente.local" }))).toBe(true);
  });

  it("rechaza otro origen, otro puerto o un esquema raro", () => {
    expect(isSameOrigin(req({ host: "192.168.1.20:3000", origin: "http://evil.example" }))).toBe(false);
    expect(isSameOrigin(req({ host: "192.168.1.20:3000", origin: "http://192.168.1.20:8080" }))).toBe(false);
    expect(isSameOrigin(req({ host: "192.168.1.20:3000", origin: "null" }))).toBe(false);
    expect(isSameOrigin(req({ host: "x:3000", origin: "file://x:3000" }))).toBe(false);
  });

  it("sin Origin (curl, servidor) no hay navegador ajeno: se deja pasar", () => {
    expect(isSameOrigin(req({ host: "192.168.1.20:3000" }))).toBe(true);
  });

  it("con Origin pero sin Host, rechaza", () => {
    expect(isSameOrigin(new Request("http://x/", { headers: { origin: "http://x" } }))).toBe(
      // `new Request` no fija Host: el navegador siempre lo manda, así que esto no es legítimo.
      false,
    );
  });
});
