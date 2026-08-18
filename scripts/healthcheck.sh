#!/usr/bin/env bash
# One-shot functional check of a running Velocity CDN deployment.
#   usage: scripts/healthcheck.sh [base-url]     default: the AWS deployment
LB="${1:-http://32.195.72.232:8080}"
ORIGIN="${LB%:8080}:8000"
pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
enc()  { python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$1"; }

echo "== endpoints =="
for p in /health /origin /edges /regions /dashboard/files \
         /dashboard/stats/hit-ratio /dashboard/stats/hit-ratio-timeseries \
         /dashboard/stats/latency /dashboard/stats/top-files \
         /dashboard/stats/edge-requests /dashboard/logs/recent; do
  c=$(curl -s -o /dev/null -m 20 -w "%{http_code}" "$LB$p")
  [ "$c" = 200 ] && ok "$p" || bad "$p returned $c"
done

echo "== services =="
curl -s -m 15 "$LB/origin" | grep -q '"status": *"healthy"' && ok "origin healthy" || bad "origin not healthy"
n=$(curl -s -m 15 "$LB/edges" | python3 -c "import json,sys;print(sum(1 for e in json.load(sys.stdin) if e['status']=='healthy'))")
[ "$n" -ge 1 ] && ok "$n edge(s) healthy" || bad "no healthy edges"
curl -s -m 15 "$LB/regions" | grep -q '"geoip_enabled": *true' && ok "geoip enabled" || bad "geoip disabled"

echo "== cache behaviour =="
KEY="hc-$(date +%s).txt"; printf 'healthcheck payload\n' > /tmp/hc.txt
curl -s -m 60 -X POST "$LB/dashboard/files?key=$KEY" -F "upload=@/tmp/hc.txt" -o /dev/null -w '' 
sleep 1
r1=$(curl -s -m 60 -D - -o /dev/null "$LB/fetch/$(enc "$KEY")?region=mumbai" | grep -i x-cache-result | tr -d '\r' | awk '{print $2}')
r2=$(curl -s -m 60 -D - -o /dev/null "$LB/fetch/$(enc "$KEY")?region=mumbai" | grep -i x-cache-result | tr -d '\r' | awk '{print $2}')
[ "$r1" = miss ] && ok "cold request is a miss" || bad "cold request was '$r1', expected miss"
[ "$r2" = hit ]  && ok "warm request is a hit"  || bad "warm request was '$r2', expected hit"

echo "== routing =="
for pair in "sydney:edge-singapore" "sao_paulo:edge-frankfurt" "delhi:edge-mumbai"; do
  city="${pair%%:*}"; want="${pair##*:}"
  got=$(curl -s -m 60 -D - -o /dev/null "$LB/fetch/$(enc "$KEY")?region=$city" | grep -i x-served-by | tr -d '\r' | awk '{print $2}')
  [ "$got" = "$want" ] && ok "$city -> $got" || bad "$city -> $got (expected $want)"
done

echo "== invalidation =="
printf 'v2 payload\n' > /tmp/hc2.txt
curl -s -m 60 -X POST "$LB/dashboard/files?key=$KEY" -F "upload=@/tmp/hc2.txt" -o /dev/null
body=$(curl -s -m 60 "$LB/fetch/$(enc "$KEY")?region=mumbai")
[ "$body" = "v2 payload" ] && ok "update purged stale copy" || bad "served stale after update: '$body'"

echo "== range requests (needed for video seek) =="
code=$(curl -s -o /dev/null -m 60 -w "%{http_code}" -H "Range: bytes=0-99" "$LB/fetch/$(enc "$KEY")")
[ "$code" = 206 ] && ok "range supported (206)" || bad "range NOT supported (got $code, need 206 for video seeking)"

echo "== cleanup =="
curl -s -m 60 -X DELETE "$LB/dashboard/files/$(enc "$KEY")" -o /dev/null && ok "delete works"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
