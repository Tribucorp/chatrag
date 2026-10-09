import { describe, expect, it } from "vitest";
import { rolesToAcls } from "./acl";

describe("rolesToAcls", () => {
  it("el rol member (default) no da ninguna ACL extra", () => {
    expect(rolesToAcls("member")).toEqual([]);
  });

  it("mapea rrhhStaff/finanzasStaff a su ACL correspondiente", () => {
    expect(rolesToAcls("rrhhStaff")).toEqual(["rrhh"]);
    expect(rolesToAcls("finanzasStaff")).toEqual(["finanzas"]);
  });

  it("municipalAdmin ve todas las ACLs del demo", () => {
    expect(rolesToAcls("municipalAdmin")).toEqual(["rrhh", "finanzas"]);
  });

  it("fail-closed: sin rol o rol desconocido, ninguna ACL extra", () => {
    expect(rolesToAcls(null)).toEqual([]);
    expect(rolesToAcls(undefined)).toEqual([]);
    expect(rolesToAcls("rol-que-no-existe")).toEqual([]);
  });
});
