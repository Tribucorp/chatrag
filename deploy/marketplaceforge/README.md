# ChatRAG en MarketplaceForge

Cómo se publica e instala ChatRAG en un Dell Pro Max GB10 / DGX Spark (ARM64) con `sparkd`.
Contrato: `Tribucorp/sparkhub` → `.github/workflows/build-demo.yml` y
`_producto/docs/claude/04-pipeline-demos.md`; esquema estricto del spec en
`packages/shared/src/mqtt/desired.ts` (`composeSpecIngestSchema`).

## Piezas

| Fichero | Qué es |
|---|---|
| `compose.spec.yaml` | Lo que arranca `sparkd` (formato del marketplace, no docker compose). |
| `.github/workflows/build.yml` | Llama a `build-demo.yml@main` con `images`, `mirror` y `prepare_script`. |
| `deploy/marketplaceforge/preparar_build.sh` | Construye en el runner ARM64 los 7 wheels `tribu-*` (tag fijada en `backend/pyproject.toml`). |
| `deploy/Dockerfile.frontend` | Imagen principal (`app`). Monta el secreto de BuildKit `node_auth_token` para `@tribu/auth`. |
| `deploy/Dockerfile.backend.protegido` | Imagen `api`: compilada con Nuitka, sin código fuente. Sin `CHATRAG_LICENSE_KEYS` (el pipeline no pasa build args) sale **sin puerta de licencia por host**: quién instala lo controla la plataforma. |

## Imágenes para el catálogo

**Propias** (las construye, escanea y firma el pipeline):
- `app` ← `deploy/Dockerfile.frontend`
- `api` ← `deploy/Dockerfile.backend.protegido` (variante sin puerta; ver arriba)

**`mirror`** (terceros, por digest; el pipeline las copia, escanea y firma):
- `etcd` ← `quay.io/coreos/etcd@sha256:d0a641d5fbcc89678c931a61b7de7b8a1cf097149f135c9c73bc81d076a1494b` (v3.5.18)
- `milvus` ← `docker.io/milvusdb/milvus@sha256:fb57464669737ee9a9c43c6faa891527adab601241b0b488091c5f4eb4a13178` (v2.6.5)

**`ngcImages`** (las descarga el equipo con la clave NGC del partner; tal cual, en este orden):
- `nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark:1.0.0-variant`
- `nvcr.io/nim/nvidia/magpie-tts-multilingual:1.10.0`
- `nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual@sha256:670db8fb668142017a12ef6fef1834e37119c3cd03180b87e5c26deb830d87d3`
- `nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:1`
- `nvcr.io/nim/nvidia/llama-nemotron-rerank-vl-1b-v2:2.3`

Sin MinIO: Milvus usa almacenamiento local en su volumen (probado en spark-da29: insertar, flush,
buscar y reiniciar). Las imágenes comunitarias de MinIO ya no se publican (Docker Hub y quay.io
responden "no existe / no autorizado").

## Memoria estimada (121 GB unificados del GB10)

| Servicio | Memoria | Origen del dato |
|---|---|---|
| nim-chat (Nemotron Nano 9B, `NIM_GPU_MEM_FRACTION=0.30`) | ~36 GB | medido en spark-69f8 (vLLM) |
| nim-asr (Parakeet 1.1b, modo offline) | ~25,6 GB | matriz de soporte de NVIDIA, **sin medir** |
| nim-tts (Magpie) | ~12,7 GB | medido en spark-69f8 (X9Voz) |
| nim-rerank | ~5,3 GB | medido en spark-69f8 |
| nim-embed | ~4,4 GB | medido en spark-69f8 |
| milvus + etcd + api + app | ~5 GB | límites `memLimit` del spec (8+1+3+2 GB, techo) |
| **Total** | **~89 GB** | ~32 GB de margen |

## Primer arranque

1. `api` genera los secretos en el volumen `chatrag-secretos` (`CHATRAG_GENERATE_SECRETS=1`):
   bearer de servicio, bearer de admin y secreto de sesión. Nadie los teclea.
2. Copia el corpus de ejemplo (Ventisca TI, empresa ficticia de soporte de servidores Dell
   PowerEdge) a `chatrag-knowledge` y lo ingiere en Milvus cuando el NIM de embeddings responde
   (`CHATRAG_AUTO_INGEST=1`). Hasta entonces el chat responde "arrancando".
3. La primera vez cada NIM descarga su modelo: 20-30 min.

Acceso: `http://<IP del equipo>:3000` desde la red del cliente (sin URL fija: `auth.ts`).
Cuentas demo en `/login` mientras `CHATRAG_AUTH_DEMO_SEED=1`. El micrófono solo funciona en https
o en el propio equipo (`localhost`).

## Variables que puede cambiar el partner (portal)

| Variable (servicio) | Por defecto | Para qué |
|---|---|---|
| `CHATRAG_AUTH_DEMO_SEED` (app) | `1` | `0` en un cliente real: sin cuentas demo de contraseña pública |
| `CHATRAG_VOICE_ENABLED` (app, api) | `1` | `0` para solo texto (y no hacen falta los NIM de voz) |
| `CHATRAG_AUTH_PROTOCOL` (app) | `http` | `https` si hay TLS delante |
| `CHATRAG_ALLOWED_HOSTS` (app) | `*` | Restringir a la IP/nombre del equipo |

## Validar el spec

```bash
ruby -ryaml -rjson -e 'puts JSON.generate(YAML.load_file("compose.spec.yaml"))' > /tmp/spec.json
cd ~/repositorio/marketplaceforge/packages/shared && ./node_modules/.bin/tsx -e '
import { readFileSync } from "node:fs";
import { composeSpecIngestSchema } from "./src/mqtt/desired.ts";
const r = composeSpecIngestSchema.safeParse(JSON.parse(readFileSync("/tmp/spec.json", "utf8")));
console.log(r.success ? "VÁLIDO" : r.error.issues);'
```

## Alta en la plataforma (una vez, la hace Javier)

El build no se lanza a mano: lo dispara la API de MarketplaceForge al recibir un push a `main`
(canal beta, versión = sha[0:12]) o a un tag (stable), y es ella quien crea el `build_id`. Antes
del primer build hace falta, en `Tribucorp/sparkhub`:

1. Dar de alta la demo `chatrag` y vincular el repo (script de catálogo como
   `apps/api/scripts/catalogo-showrunforge.ts`, con `--solo-registro`), con sus requisitos y los
   `ngcImages` de arriba.
2. Webhook de push en `Tribucorp/chatrag` → `https://api.tribucorp.es/v1/webhooks/github`.
3. Acceso del PAT de disparo (`GITHUB_BUILD_DISPATCH_TOKEN`, `actions:write`) a este repo.

Tras el primer build, el mismo script sin `--solo-registro` la añade al plan.

## Verificado en local (16-nov)

Imágenes construidas como en el pipeline (`chatrag-api` protegida sin claves, `chatrag-frontend`)
y arrancadas con la configuración del spec (solo lectura, `capDrop: ALL`, volumen de secretos
compartido): secretos 0600 de UID 10001, `/health` con licencia `desactivada`, login demo, chat
503 «arrancando» sin Milvus, admin solo con la sesión (cliente 403), CSRF 403 con Origin ajeno y
sesión que sobrevive al reinicio. Spec válido contra `composeSpecIngestSchema` de sparkhub `main`.
