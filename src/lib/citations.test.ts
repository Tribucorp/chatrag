import { describe, expect, it } from "vitest";
import { stripCiteMarkers } from "./citations";

describe("stripCiteMarkers", () => {
  it("quita las marcas y el espacio previo", () => {
    expect(stripCiteMarkers("Abre de 9 a 14 [1]. Cierra en agosto [2][3].")).toBe(
      "Abre de 9 a 14. Cierra en agosto.",
    );
  });

  it("no toca enlaces Markdown ni corchetes que no son citas", () => {
    expect(stripCiteMarkers("Ver [la guía](https://x.cl) y [nota]")).toBe(
      "Ver [la guía](https://x.cl) y [nota]",
    );
  });
});
