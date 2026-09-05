# Legacy — tooling de ElevenLabs (pre-SDK)

Estos scripts pertenecen al **prototipo anterior** de ChatRAG, cuando la voz y la base de
conocimiento vivían en **ElevenLabs** (proveedor cloud). Se conservan solo como referencia
funcional.

**No forman parte del producto sobre el Tribu SDK** y no deben ejecutarse en producción: el SDK
es on-prem y NVIDIA-native, la voz la da `tribu-voice` (Riva stock, sin clonación, hoy tras flag
apagado por revisión legal), y la ingesta de la base de conocimiento la hace `tribu-rag` (guard
de dimensión 2048). Cuando la ingesta con `tribu-rag` esté cableada, estos scripts se eliminan.

- `create-agent.ts` — provisionaba un agente conversacional en ElevenLabs.
- `upload-kb.ts` — subía la carpeta `knowledge/` a la KB de ElevenLabs.
- `crawl-site-to-kb.ts` — crawl de munistgo.cl hacia la KB de ElevenLabs.
