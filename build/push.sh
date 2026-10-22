#!/usr/bin/env bash
# Push MATHEMATICA to GitHub without ever writing the token into
# .git/config or the remote URL.
#
#   GH_TOKEN=github_pat_xxx ./build/push.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TOKEN="${GH_TOKEN:-$(cat /tmp/opencode/.gh-token 2>/dev/null || true)}"
if [ -z "$TOKEN" ]; then
  echo "set GH_TOKEN=github_pat_xxx" >&2
  exit 1
fi

REMOTE="${GH_REMOTE:-https://github.com/Pratyush-bit69/mathematica.git}"

git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"

AUTH=$(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)
git -c http.https://github.com/.extraheader="AUTHORIZATION: basic $AUTH" \
    push -u origin main

echo
echo "pushed. private: $(curl -sS -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/vnd.github+json' \
  https://api.github.com/repos/Pratyush-bit69/mathematica \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("private"))')"
