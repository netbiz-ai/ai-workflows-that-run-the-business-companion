#!/usr/bin/env bash
# Run one recipe's golden set on Make from the companion test stack (VPS) and fetch the results.
#   tools/make/remote-test.sh R11.2 [--case Normal ...]
# The stack keeps the Make token in make.env and the public test route's secret in ids.env,
# both readable by root only; nothing secret passes through this machine.
set -euo pipefail
RID="$1"; shift
ARGS=""; [ $# -gt 0 ] && ARGS=$(printf '%q ' "$@")
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${COMPANION_HOST:?set COMPANION_HOST to user@host of your test stack}"
KEY="${COMPANION_KEY:?set COMPANION_KEY to your SSH key path}"
PUBLIC_HOST="${COMPANION_PUBLIC_HOST:?set COMPANION_PUBLIC_HOST to the test route host, such as companion-mocks.example.com}"
REMOTE=/opt/companion-n8n/repo
SSH="ssh -i $KEY $HOST"
$SSH "mkdir -p $REMOTE/recipes/$RID $REMOTE/tools/make $REMOTE/tools/builds_make"
for d in n8n builds make builds_make; do
  rsync -a -e "ssh -i $KEY" "$ROOT/tools/$d/" "$HOST:$REMOTE/tools/$d/"
done
rsync -a -e "ssh -i $KEY" "$ROOT/recipes/$RID/" "$HOST:$REMOTE/recipes/$RID/"
set +e
$SSH "cd /opt/companion-n8n && set -a && . ./make.env && . ./ids.env && set +a && export MOCKS_PUBLIC_URL=https://$PUBLIC_HOST/\$MOCKS_PUBLIC_SECRET MAKE_ADOPT_SCENARIOS=${MAKE_ADOPT_SCENARIOS:-} MAKE_MIN_CREDITS=${MAKE_MIN_CREDITS:-1500} && cd repo && python3 tools/make/golden_make.py $RID $ARGS"
status=$?
set -e
rsync -a -e "ssh -i $KEY" "$HOST:$REMOTE/recipes/$RID/make/" "$ROOT/recipes/$RID/make/"
exit $status
