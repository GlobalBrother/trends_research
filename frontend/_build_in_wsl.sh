#!/usr/bin/env bash
set -euo pipefail
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
nvm use 24.14.0 >/dev/null
corepack enable >/dev/null 2>&1 || true
corepack prepare pnpm@latest --activate >/dev/null 2>&1 || true

SRC="/mnt/c/Users/MarianCraciun/OneDrive - Global Brother SRL/Documents/GitHub/trends_research/frontend"
WORK="$HOME/_fe_build"

echo "node: $(node --version)"
echo "pnpm: $(pnpm --version)"

rm -rf "$WORK"
mkdir -p "$WORK"

# Copy only the files needed to build (no node_modules / dist).
# OneDrive on /mnt/c breaks pnpm's atomic renames with EACCES, so we build
# in WSL's native filesystem and copy the dist back when done.
echo "[1/4] copying frontend source into $WORK ..."
# rsync isn't installed by default on plain WSL; use tar to copy with excludes.
( cd "$SRC" && tar --exclude=node_modules --exclude=dist --exclude=.turbo --exclude=.vite -cf - . ) \
    | ( cd "$WORK" && tar -xf - )

cd "$WORK"

echo "[2/4] pnpm install ..."
pnpm install --frozen-lockfile

echo "[3/4] pnpm build ..."
pnpm build

echo "[4/4] copying dist back to $SRC/dist ..."
rm -rf "$SRC/dist"
mkdir -p "$SRC/dist"
cp -r dist/. "$SRC/dist/"

echo "DONE. dist contents:"
ls -la "$SRC/dist" | head -20


