#!/usr/bin/env bash
# Run one recipe's golden set on the companion test stack (VPS) and fetch the results.
#   tools/n8n/remote-test.sh R11.2
# Syncs only the recipe's own files and the shared tools, so builders working on
# other recipes are not disturbed; golden.py itself serialises runs with a lock.
set -euo pipefail
RID="$1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${COMPANION_HOST:?set COMPANION_HOST to user@host of your test stack}"
KEY="${COMPANION_KEY:?set COMPANION_KEY to your SSH key path}"
REMOTE=/opt/companion-n8n/repo
BUILD="tools/builds/r${RID#R}"; BUILD="${BUILD//./_}.py"
SSH="ssh -i $KEY $HOST"
$SSH "mkdir -p $REMOTE/recipes/$RID/n8n $REMOTE/tools/builds"
rsync -a -e "ssh -i $KEY" "$ROOT/tools/n8n/" "$HOST:$REMOTE/tools/n8n/"
rsync -a -e "ssh -i $KEY" "$ROOT/$BUILD" "$HOST:$REMOTE/$BUILD"
rsync -a -e "ssh -i $KEY" "$ROOT/recipes/$RID/" "$HOST:$REMOTE/recipes/$RID/"
set +e
$SSH "cd /opt/companion-n8n && . ./api.env && set -a && . ./ids.env && set +a && export N8N_API_KEY && cd repo && python3 tools/n8n/golden.py $RID"
status=$?
set -e
rsync -a -e "ssh -i $KEY" "$HOST:$REMOTE/recipes/$RID/n8n/" "$ROOT/recipes/$RID/n8n/"
exit $status
