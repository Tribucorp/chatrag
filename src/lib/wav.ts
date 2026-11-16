/**
 * Audio del micrófono → WAV PCM16 16 kHz mono, lo que espera el NIM de ASR de Riva (Parakeet).
 * MediaRecorder graba en webm/opus, que el NIM no acepta; convertir aquí evita meter ffmpeg en
 * el backend. `encodeWavPcm16` es puro (testeable); `blobToWav16kMono` usa Web Audio.
 */

export const ASR_SAMPLE_RATE_HZ = 16_000;

/** Muestras float [-1, 1] mono → fichero WAV PCM16 little-endian. */
export function encodeWavPcm16(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // tamaño del bloque fmt
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits por muestra
  writeAscii(36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** Grabación (cualquier formato que el navegador sepa decodificar) → WAV 16 kHz mono. */
export async function blobToWav16kMono(blob: Blob): Promise<Blob> {
  const ctx = new AudioContext();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const frames = Math.max(1, Math.ceil(decoded.duration * ASR_SAMPLE_RATE_HZ));
    // OfflineAudioContext con 1 canal mezcla a mono y remuestrea a 16 kHz.
    const offline = new OfflineAudioContext(1, frames, ASR_SAMPLE_RATE_HZ);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return new Blob([encodeWavPcm16(rendered.getChannelData(0), ASR_SAMPLE_RATE_HZ)], {
      type: "audio/wav",
    });
  } finally {
    void ctx.close();
  }
}
