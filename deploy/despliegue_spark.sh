#!/usr/bin/env bash
# Fase D — despliegue de ChatRAG en una DGX Spark, offline. Se ejecuta DESDE EL MAC (no desde
# el Spark). Adapta t6_sesion_spark.sh de tribu-sdk (mismo patrón de fases por SSH, idempotente,
# se puede relanzar) a lo que ChatRAG necesita: construir los wheels tribu-* desde el código
# fuente (el registry privado no es alcanzable desde este Spark, ver deploy/Dockerfile.backend)
# en vez de un `uv sync` normal contra el índice `tribu`.
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

# ── FASE 2 · Wheels tribu-* construidos desde el código fuente ──────────────
if corre 2; then
  azul "FASE 2 · Wheels tribu-* (registry privado NO alcanzable desde este Spark — ver deploy/Dockerfile.backend)"
  mkdir -p "$LOCAL_REPO/deploy/wheels"
  echo "  → 4 wheels puros (portables, se construyen en el Mac): tribu-http/tribu-rag/tribu-guardrails/tribu-voice"
  ( cd "$LOCAL_SDK" && uv build --package tribu-http --package tribu-rag \
      --package tribu-guardrails --package tribu-voice -o "$LOCAL_REPO/deploy/wheels" 2>&1 | tail -8 )
  echo "  → tribu-audit tiene una extensión nativa (PyO3/Rust): se construye EN el Spark (aarch64 Linux), no en el Mac"
  sh_spark "command -v cargo >/dev/null" || fallo "falta Rust en el Spark — curl -LsSf https://sh.rustup.rs | sh -s -- -y"
  sh_spark "command -v \$HOME/.local/bin/uv >/dev/null" || fallo "falta uv en el Spark — curl -LsSf https://astral.sh/uv/install.sh | sh"
  sh_spark "cd $SDK_DIR && \$HOME/.local/bin/uv build --package tribu-audit -o /tmp/chatrag-wheels 2>&1 | tail -8"
  scp -i "$SPARK_KEY" "$SPARK_SSH:/tmp/chatrag-wheels/tribu_audit-0.1.0-*.whl" "$LOCAL_REPO/deploy/wheels/" \
    || fallo "no pude traer el wheel de tribu-audit del Spark"
  ls "$LOCAL_REPO/deploy/wheels"/*.whl | sed 's/^/  /'
  ok "5 wheels tribu-* listos en deploy/wheels/ (no versionados, ver .gitignore)"
fi

# ── FASE 3 · Repos en el Spark (rsync — sin credenciales git en el Spark) ───
if corre 3; then
  azul "FASE 3 · Repos en el Spark"
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
  for IMG in "$NIM_CHAT_IMAGE" "$NIM_EMBED_IMAGE" "$NIM_RERANK_IMAGE"; do
    echo "  → pull $IMG"
    sh_spark "docker pull '$IMG'" || fallo "pull de $IMG"
  done
  ok "imágenes NIM en el Spark"
fi

# ── FASE 5 · docker compose up ───────────────────────────────────────────────
if corre 5; then
  azul "FASE 5 · docker compose (build + up)"
  sh_spark "cat > $REPO_DIR/deploy/.env.chatrag-spark && chmod 600 $REPO_DIR/deploy/.env.chatrag-spark" < "$ENVFILE"
  sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml build"
  sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml up -d"
  echo "  → esperando salud de los servicios (el primer arranque de un NIM descarga el modelo: puede tardar)"
  for i in $(seq 1 90); do
    ESTADO=$(sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml ps --format '{{.Name}} {{.Health}}'" 2>/dev/null || true)
    echo "$ESTADO" | sed 's/^/    /'
    echo "$ESTADO" | grep -vq -E 'healthy|^$' || { ok "todos los servicios healthy"; break; }
    sleep 20
  done

  azul "Guardia · los servicios solo escuchan en 127.0.0.1 salvo que se haya fijado explícitamente"
  for SVC in nim-chat nim-embed nim-rerank chatrag-api frontend; do
    BINDING=$(sh_spark "cd $REPO_DIR && docker compose --env-file deploy/.env.chatrag-spark -f deploy/docker-compose.chatrag-spark.yml port $SVC $([ "$SVC" = chatrag-api ] && echo 8080 || ([ "$SVC" = frontend ] && echo 3000 || echo 8000))" 2>/dev/null)
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
  4. Sin CHATRAG_DEV_IDENTITY_BYPASS ni tribu-auth real, /query devuelve 401 a cualquier
     visitante real — decide con Javier si este despliegue necesita el bypass de dev o espera
     a un proveedor SSO real (ver CLAUDE.md).
FIN
fi
