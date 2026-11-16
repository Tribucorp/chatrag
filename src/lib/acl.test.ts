import { describe, expect, it } from "vitest";
import { isAdminRole, rolesToAcls } from "./acl";

describe("rolesToAcls", () => {
  it("el cliente no tiene ACL extra (solo lo público)", () => {
    expect(rolesToAcls("cliente")).toEqual([]);
  });

  it("técnico y comercial ven su área interna", () => {
    expect(rolesToAcls("tecnico")).toEqual(["soporte"]);
    expect(rolesToAcls("comercial")).toEqual(["comercial"]);
  });

  it("adminSoporte ve todas las áreas internas", () => {
    expect(rolesToAcls("adminSoporte")).toEqual(["soporte", "comercial"]);
  });

  it("fail-closed: sin rol o rol desconocido, ninguna ACL extra", () => {
    expect(rolesToAcls(null)).toEqual([]);
    expect(rolesToAcls(undefined)).toEqual([]);
    expect(rolesToAcls("rol-que-no-existe")).toEqual([]);
    expect(rolesToAcls("toString")).toEqual([]);
    expect(rolesToAcls("__proto__")).toEqual([]);
  });

  it("devuelve una copia: mutarla no altera los grants", () => {
    rolesToAcls("tecnico").push("comercial");
    expect(rolesToAcls("tecnico")).toEqual(["soporte"]);
  });
});

describe("isAdminRole", () => {
  it("solo adminSoporte administra", () => {
    expect(isAdminRole("adminSoporte")).toBe(true);
    for (const rol of ["cliente", "tecnico", "comercial", "", null, undefined]) {
      expect(isAdminRole(rol)).toBe(false);
    }
  });
});
