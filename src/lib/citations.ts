// Marcas de cita que el backend deja en el texto (`[1]`, `[2][3]`, ya renumeradas para que
// `[n]` sea la n-ésima cita devuelta — ver `select_cited` en backend/src/chatrag_api/rag.py).
const CITE_MARKERS = /[ \t]*(?:\[\d{1,3}\])+/g;

/** Texto sin marcas de cita: para leerlo en voz alta o cuando la UI oculta las fuentes. */
export function stripCiteMarkers(text: string): string {
  return text.replace(CITE_MARKERS, "");
}
