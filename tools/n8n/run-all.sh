#!/usr/bin/env bash
# Run every recipe's golden set on the test stack, in book order; one summary line each.
#   tools/n8n/run-all.sh [R4.1 R4.2 ...]     run on the stack host, from the repository root
set -uo pipefail
cd "$(dirname "$0")/../.."
ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  mapfile -t ids < <(ls recipes | sort -t. -k1.2n -k2n)
fi
for rid in "${ids[@]}"; do
  out=$(python3 tools/n8n/golden.py "$rid" 2>&1)
  fails=$(grep -c '^FAIL' <<<"$out")
  passes=$(grep -c '^PASS' <<<"$out")
  skips=$(grep -c '^SKIP' <<<"$out")
  err=$(grep -m1 -E 'Error|Traceback' <<<"$out")
  printf '%-6s pass %2d  fail %2d  skip %2d  %s\n' "$rid" "$passes" "$fails" "$skips" "${err:0:120}"
  grep -A3 '^FAIL' <<<"$out" | sed 's/^/        /'
done
