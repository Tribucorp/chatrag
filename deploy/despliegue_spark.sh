#!/usr/bin/env bash
# Fase D — despliegue de ChatRAG en una DGX Spark, offline. Se ejecuta DESDE EL MAC (no desde
# el Spark). Adapta t6_sesion_spark.sh de tribu-sdk (mismo patrón de fases por SSH, idempotente,
# se puede relanzar) a lo que ChatRAG necesita: construir los wheels tribu-* desde la tag del
# SDK que fija backend/pyproject.toml (el Spark no tiene credenciales git para resolver las
# dependencias git de ADR-0020, ver deploy/Dockerfile.backend) en vez de un `uv sync` normal.
#
# Uso:
#   bash deploy/despliegue_spark.sh            # todas las fases en orden
#   bash deploy/despliegue_spark.sh 3          # solo la fase 3
#
# Requisitos en el Mac: alias SSH "chatrag-spark" en ~/.ssh/config (o SPARK_HOST=usuario@host),
# deploy/.env.chatrag-spark rellenado, y ~/repositorio/tribu-sdk clonado localmente (fuente
# real de los wheels tribu-*, ver fase 2).
set -euo pipefail

SPARK="${SPARK_HOST:-spark-da29.taild09659.ts.net}"
SPARK_SSH="${SPARK_SSH_USER:-administrador}@${SPARK}"
SPARK_KEY="${SPARK_SSH_KEY:-$HOME/.ssh/id_ed25519}"
REPO_DIR="\$HOME/repositorio/chatrag"
SDK_DIR="\$HOME/repositorio/tribu-sdk"
LOCAL_REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_SDK="$(cd "$LOCAL_REPO/../tribu-sdk" 2>/dev/null && pwd || echo "")"
ENVFILE="$LOCAL_REPO/deploy/.env.chatrag-spark"
FASE="${1:-todas}"

azul(){ printf '\n\033[1;34m══ %s ══\033[0m\n' "$*"; }
ok(){ printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
fallo(){ printf '\033[1;31m  ✗ %s\033[0m\n' "$*"; exit 1; }
sh_spark(){ ssh -i "$SPARK_KEY" -o ConnectTimeout=10 "$SPARK_SSH" "$@"; }
corre(){ [ "$FASE" = "todas" ] || [ "$FASE" = "$1" ]; }

# ── FASE 0 · Conectividad + .env ─────────────────────────────────────────────
if corre 0; then
  azul "FASE 0 · Conectividad desde el Mac"
  sh_spark true || fallo "SSH a '$SPARK_SSH' no responde."
  ok "SSH a $SPARK_SSH funciona"
  [ -f "$ENVFILE" ] || fallo "falta $ENVFILE — copia deploy/.env.chatrag-spark.example y rellena"
  grep -q "changeme" "$ENVFILE" && fallo ".env.chatrag-spark aún tiene valores 'changeme'"
  grep -qE '^NGC_API_KEY=.+' "$ENVFILE" || fallo "falta NGC_API_KEY en $ENVFILE (los NIM la necesitan para bajar sus modelos)"
  ok ".env.chatrag-spark presente y sin placeholders"
  [ -n "$LOCAL_SDK" ] || fallo "no encuentro ~/repositorio/tribu-sdk junto a este repo — hace falta como fuente de los wheels tribu-* (fase 2)"
  ok "tribu-sdk local encontrado en $LOCAL_SDK"
fi

# ── FASE 1 · Salud del Spark (GPU, Docker, disco) ────────────────────────────
if corre 1; then
  azul "FASE 1 · Salud del Spark (GPU, Docker, disco)"
  sh_spark "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" || fallo "nvidia-smi falla"
  sh_spark "docker info --format '{{.Runtimes}}' | grep -qi nvidia" || fallo "Docker sin runtime NVIDIA (ver nvidia-ctk runtime configure --runtime=docker)"
  LIBRE=$(sh_spark "df -BG --output=avail / | tail -1 | tr -dc '0-9'")
  [ "$LIBRE" -ge 40 ] || fallo "solo ${LIBRE}G libres — los 3 NIM + Milvus necesitan margen"
  ok "GPU visible, runtime NVIDIA, ${LIBRE}G libres"
fi

# ── FASE 2 · Wheels tribu-* construidos desde el tag del SDK ────────────────
# El Spark no tiene credenciales git de Tribucorp (deliberado), así que no puede resolver las
# dependencias git de backend/pyproject.toml (ADR-0020 del SDK). Los wheels se construyen desde
# un `git archive` del MISMO tag que fija uv.lock — nunca desde el checkout de trabajo del SDK,
# que puede ir por delante o por detrás de la release probada en CI.
if corre 2; then
  SDK_TAG=$(grep -m1 -o 'tag = "v[0-9.]*"' "$LOCAL_REPO/backend/pyproject.toml" | cut -d'"' -f2)
  [ -n "$SDK_TAG" ] || fallo "no encuentro la tag del SDK en backend/pyproject.toml"
  azul "FASE 2 · Wheels tribu-* desde tribu-sdk@$SDK_TAG"
  git -C "$LOCAL_SDK" fetch -q --tags origin || fallo "no pude traer las tags de tribu-sdk"
  EXPORT="$(mktemp -d)/tribu-sdk-$SDK_TAG"; mkdir -p "$EXPORT"
  git -C "$LOCAL_SDK" archive "$SDK_TAG" python rust Cargo.toml Cargo.lock rust-toolchain.toml \
    | tar -x -C "$EXPORT" || fallo "git archive $SDK_TAG"
  rm -rf "$LOCAL_REPO/deploy/wheels"; mkdir -p "$LOCAL_REPO/deploy/wheels"
  echo "  → 4 wheels puros (portables, se construyen en el Mac): tribu-http/tribu-rag/tribu-guardrails/tribu-voice"
  for PKG in tribu-http tribu-rag tribu-guardrails tribu-voice; do
    ( cd "$EXPORT/python/$PKG" && uv build --wheel -o "$LOCAL_REPO/deploy/wheels" 2>&1 | tail -1 ) \
      || fallo "build de $PKG"
  done
  echo "  → tribu-audit y tribu-crypto tienen núcleo Rust (PyO3): se construyen EN el Spark (aarch64 Linux)"
  sh_spark "command -v cargo >/dev/null || [ -x \$HOME/.cargo/bin/cargo ]" || fallo "falta Rust en el Spark — curl -LsSf https://sh.rustup.rs | sh -s -- -y"
  sh_spark "command -v \$HOME/.local/bin/uv >/dev/null" || fallo "falta uv en el Spark — curl -LsSf https://astral.sh/uv/install.sh | sh"
  sh_spark "rm -rf /tmp/chatrag-sdk /tmp/chatrag-wheels && mkdir -p /tmp/chatrag-sdk"
  tar -C "$EXPORT" -c . | sh_spark "tar -x -C /tmp/chatrag-sdk" || fallo "copia del export al Spark"
  for PKG in tribu-audit tribu-crypto; do
    sh_spark "cd /tmp/chatrag-sdk/python/$PKG && PATH=\$HOME/.cargo/bin:\$PATH \$HOME/.local/bin/uv build --wheel -o /tmp/chatrag-wheels 2>&1 | tail -1" \
      || fallo "build de $PKG en el Spark"
  done
  scp -i "$SPARK_KEY" "$SPARK_SSH:/tmp/chatrag-wheels/*.whl" "$LOCAL_REPO/deploy/wheels/" \
    || fallo "no pude traer los wheels nativos del Spark"
  ls "$LOCAL_REPO/deploy/wheels"/*.whl | sed 's/^/  /'
  [ "$(ls "$LOCAL_REPO/deploy/wheels"/*.whl | wc -l)" -eq 6 ] || fallo "esperaba 6 wheels tribu-*"
  ok "6 wheels tribu-* de $SDK_TAG en deploy/wheels/ (no versionados, ver .gitignore)"
fi

# ── FASE 3 · Repos en el Spark (rsync — sin credenciales git en el Spark) ───
if corre 3; then
  azul "FASE 3 · Repos en el Spark"
  # rsync no crea directorios intermedios: en un Spark recién usado no existe ~/repositorio.
  sh_spark "mkdir -p repositorio/chatrag repositorio/tribu-sdk/python/tribu-rag/deploy"
  rsync -az --delete --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
    --exclude 'target' --exclude 'rust' --exclude 'scripts' --exclude '.mypy_cache' \
    --exclude '__pycache__' -e "ssh -i $SPARK_KEY" \
    "$LOCAL_SDK/python/tribu-rag/deploy/" "$SPARK_SSH:repositorio/tribu-sdk/python/tribu-rag/deploy/"
  rsync -az --delete --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
    --exclude '.next' --exclude '.mypy_cache' --exclude '__pycache__' -e "ssh -i $SPARK_KEY" \
    "$LOCAL_REPO/" "$SPARK_SSH:repositorio/chatrag/"
  ok "repos sincronizados en el Spark"
fi

# ── FASE 4 · NGC login + pull de NIMs (lo largo: decenas de GB) ─────────────
if corre 4; then
  azul "FASE 4 · NGC login + pull de NIMs (paciencia)"
  set -a; source "$ENVFILE"; set +a
  sh_spark "echo '$NGC_API_KEY' | docker login nvcr.io -u '\$oauthtoken' --password-stdin" || fallo "login nvcr.io"
  NIM_TTS_IMAGE="${NIM_TTS_IMAGE:-nvcr.io/nim/nvidia/magpie-tts-multilingual:1.10.0}"
  NIM_ASR_IMAGE="${NIM_ASR_IMAGE:-nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual@sha256:670db8fb668142017a12ef6fef1834e37119c3cd03180b87e5c26deb830d87d3}"
  for IMG in "$NIM_CHAT_IMAGE" "$NIM_EMBED_IMAGE" "$NIM_RERANK_IMAGE" "$NIM_TTS_IMAGE" "$NIM_ASR_IMAGE"; do
    echo "  → pull $IMG"
    sh_spark "docker pull '$IMG'" || fallo "pull de $IMG"
  done
  ok "imágenes NIM en el Spark"
fi

# ── FASE 5 · docker compose up ───────────────────────────────────────────────
if corre 5; then
  azul "FASE 5 · docker compose (build + up)"
  sh_spark "cat > $REPO_DIR/deploy/.env.chatrag-spark && chmod 600 $REPO_DIR/deploy/.env.chatrag-spark" < "$ENVFILE"
  # @tribu/auth (frontend) sale de GitHub Packages: token read:packages del Mac (gh) enviado por
  # stdin — nunca en la línea de comandos remota (visible en `ps`) ni escrito a disco en el Spark.
  NPM_TOKEN="${NODE_AUTH_TOKEN:-$(gh auth token 2>/dev/null || true)}"
  [ -n "$NPM_TOKEN" ] || fallo "sin token para GitHub Packages: exporta NODE_AUTH_TOKEN o haz gh auth login"
  printf '%s' "$NPM_TOKEN" | sh_spark "cd $REPO_DIR && NODE_AUTH_TOKEN=\$(cat) docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml build"
  sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml up -d"
  echo "  → esperando salud de los servicios (el primer arranque de un NIM descarga el modelo: puede tardar)"
  # Hasta 60 min: el primer arranque de los NIM de Riva descarga y optimiza el modelo.
  for i in $(seq 1 180); do
    ESTADO=$(sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml ps --format '{{.Name}} {{.Health}}'" 2>/dev/null || true)
    echo "$ESTADO" | sed 's/^/    /'
    # Comparación exacta: `grep healthy` también casaría "unhealthy".
    PENDIENTES=$(echo "$ESTADO" | awk 'NF==2 && $2!="healthy"' | wc -l | tr -d ' ')
    echo "$ESTADO" | awk '$2=="unhealthy"{exit 1}' || fallo "hay servicios unhealthy — mira docker compose logs"
    [ -n "$ESTADO" ] && [ "$PENDIENTES" = 0 ] && { ok "todos los servicios healthy"; break; }
    [ "$i" = 180 ] && fallo "tras 60 min siguen servicios sin estar healthy"
    sleep 20
  done

  azul "Guardia · los servicios solo escuchan en 127.0.0.1 salvo que se haya fijado explícitamente"
  for SVC in nim-chat nim-embed nim-rerank nim-tts nim-asr chatrag-api frontend; do
    case "$SVC" in chatrag-api) P=8080 ;; frontend) P=3000 ;; nim-tts|nim-asr) P=9000 ;; *) P=8000 ;; esac
    BINDING=$(sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml port $SVC $P" 2>/dev/null)
    echo "  $SVC → ${BINDING:-(sin publicar)}"
  done
fi

# ── FASE 6 · Ingesta del corpus con embeddings REALES ────────────────────────
if corre 6; then
  azul "FASE 6 · Ingesta del corpus knowledge/*.md (embeddings reales del NIM)"
  EMBED_ID=$(sh_spark "curl -s localhost:8002/v1/models" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])') \
    || fallo "el NIM de embeddings no responde en :8002 — ¿fase 5 completada?"
  echo "  → model_id reportado por el NIM de embeddings: $EMBED_ID"
  sh_spark "curl -s -X POST -H 'Authorization: Bearer '\"\$(grep ^CHATRAG_ADMIN_TOKEN $REPO_DIR/deploy/.env.chatrag-spark | cut -d= -f2)\" localhost:8091/admin/reindex" \
    && echo && ok "corpus ingerido" || fallo "reindex — mira: ssh $SPARK_SSH 'docker logs chatrag-chatrag-api-1'"
fi

# ── FASE 7 · Humo ─────────────────────────────────────────────────────────────
if corre 7; then
  azul "FASE 7 · Humo end-to-end"
  sh_spark "curl -sf localhost:8091/health" && echo && ok "chatrag-api /health"
  sh_spark "curl -sf localhost:3000/ -o /dev/null -w '%{http_code}'" && echo && ok "frontend responde"
  azul "SIGUIENTE (manual)"
  cat <<FIN
  1. Si necesitas alcance real desde tu Mac (no solo SSH), fija
     CHATRAG_FRONTEND_BIND_HOST/CHATRAG_API_BIND_HOST/NIM_*_BIND_HOST en
     deploy/.env.chatrag-spark a la IP Tailscale del Spark (\`tailscale ip -4\` EN el Spark) y
     relanza la fase 5 — nunca "0.0.0.0".
  2. Prueba el chat real: http://<esa IP>:3000 (o \`ssh $SPARK_SSH -L 3000:localhost:3000\`
     y abre http://localhost:3000 en tu Mac sin exponer nada en la tailnet).
  3. /admin (CHATRAG_ADMIN_TOKEN de deploy/.env.chatrag-spark) para reindexar, ver el tema,
     conversaciones y métricas de consumo del RAG.
  4. Login con tribu-auth; con CHATRAG_AUTH_DEMO_SEED=1 hay cuentas demo (ver src/lib/seed-demo.ts).
  5. La voz (micrófono) solo funciona en https o en localhost: usa el túnel SSH del punto 2.
FIN
fi
