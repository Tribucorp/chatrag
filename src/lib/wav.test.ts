import { describe, expect, it } from "vitest";
import { encodeWavPcm16 } from "./wav";

const ascii = (view: DataView, offset: number, length: number) =>
  String.fromCharCode(...Array.from({ length }, (_, i) => view.getUint8(offset + i)));

describe("encodeWavPcm16", () => {
  it("escribe una cabecera WAV PCM16 mono válida", () => {
    const view = new DataView(encodeWavPcm16(new Float32Array(10), 16_000));
    expect(ascii(view, 0, 4)).toBe("RIFF");
    expect(ascii(view, 8, 4)).toBe("WAVE");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(20); // 10 muestras × 2 bytes
    expect(view.byteLength).toBe(44 + 20);
  });

  it("convierte y recorta las muestras a int16", () => {
    const view = new DataView(encodeWavPcm16(new Float32Array([0, 1, -1, 2, -2]), 16_000));
    const muestras = [0, 1, 2, 3, 4].map((i) => view.getInt16(44 + i * 2, true));
    expect(muestras).toEqual([0, 32767, -32768, 32767, -32768]);
  });
});
