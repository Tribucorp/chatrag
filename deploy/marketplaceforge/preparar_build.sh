#!/usr/bin/env bash
# Prepara el contexto de build cuando construye MarketplaceForge (Tribucorp/sparkhub,
# .github/workflows/build-demo.yml, input prepare_script). Corre desde la raíz del repo, en el
# runner ARM64 nativo, antes de construir las imágenes; es el único paso que ve TRIBU_SDK_TOKEN.
#
# Construye los 6 wheels tribu-* que copia deploy/Dockerfile.backend (deploy/wheels/), desde la
# MISMA tag del SDK que fija backend/pyproject.toml. tribu-audit y tribu-crypto son nativos
# (PyO3/Rust): se compilan aquí en aarch64 con el toolchain que fija el propio SDK. Exigen
# GLIBC ≤ 2.34 (comprobado), por debajo de la de python:3.12-slim.
set -euo pipefail

TAG="$(grep -m1 -o 'tag = "v[0-9.]*"' backend/pyproject.toml | cut -d'"' -f2)"
[ -n "$TAG" ] || { echo "::error::no encuentro la tag del SDK en backend/pyproject.toml"; exit 2; }
[ -n "${TRIBU_SDK_TOKEN:-}" ] || { echo "::error::falta TRIBU_SDK_TOKEN (lectura sobre Tribucorp/tribu-sdk)"; exit 1; }

SDK="$(mktemp -d)/tribu-sdk"
git clone --quiet --depth 1 --branch "$TAG" \
  "https://x-access-token:${TRIBU_SDK_TOKEN}@github.com/Tribucorp/tribu-sdk.git" "$SDK"

command -v uv >/dev/null || { python3 -m pip install --quiet --user uv; export PATH="$HOME/.local/bin:$PATH"; }
if ! command -v rustup >/dev/null; then
  curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
  export PATH="$HOME/.cargo/bin:$PATH"
fi
TOOLCHAIN="$(grep -m1 '^channel' "$SDK/rust-toolchain.toml" | cut -d'"' -f2)"
rustup toolchain install "$TOOLCHAIN" --profile minimal

rm -rf deploy/wheels && mkdir -p deploy/wheels
for PKG in tribu-http tribu-rag tribu-guardrails tribu-voice tribu-audit tribu-crypto; do
  (cd "$SDK/python/$PKG" && uv build --wheel --quiet -o "$OLDPWD/deploy/wheels")
done
rm -rf "$SDK"
[ "$(ls deploy/wheels/*.whl | wc -l)" -eq 6 ] || { echo "::error::esperaba 6 wheels tribu-*"; exit 1; }
echo "SDK $TAG → deploy/wheels:"; ls deploy/wheels
