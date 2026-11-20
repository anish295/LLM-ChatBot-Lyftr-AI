#!/usr/bin/env bash
# End-to-end contract smoke test.
#   Usage: scripts/smoke_test.sh [BACKEND_URL]      (default http://localhost:8000)
# Needs: bash, curl, and python3 (or python) for JSON parsing.
set -uo pipefail

BASE="${1:-${BACKEND_URL:-http://localhost:8000}}"
BASE="${BASE%/}"
PY=""
for c in python3 python py; do # first interpreter that actually runs (skips Windows Store stubs)
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import json,sys; sys.exit(0)' >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "python3 is required for JSON parsing"; exit 2; }

if [ -t 1 ] || [ -n "${FORCE_COLOR:-}" ]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'; else G=; R=; Y=; B=; N=; fi
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ${G}PASS${N} $*"; }
bad()  { FAIL=$((FAIL+1)); echo "  ${R}FAIL${N} $*"; }
step() { echo; echo "${B}== $* ==${N}"; }

TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
NONCE="$(date +%s)$RANDOM"

# req METHOD PATH [JSON_BODY] [EXTRA_HEADER] -> sets $CODE and $BODY
req() {
  local method="$1" path="$2" data="${3:-}" header="${4:-}"
  local args=(-sS -o "$TMPD/body" -w '%{http_code}' -X "$method" "$BASE$path" --max-time 120)
  [ -n "$data" ] && args+=(-H 'Content-Type: application/json' --data-binary "$data")
  [ -n "$header" ] && args+=(-H "$header")
  CODE="$(curl "${args[@]}" 2>"$TMPD/err" || echo 000)"
  BODY="$(cat "$TMPD/body" 2>/dev/null)"
}
# jget EXPR -> evaluates a Python expression against the parsed body `j`
jget() { printf '%s' "$BODY" | "$PY" -c "import sys,json
try: j=json.load(sys.stdin)
except Exception: print('<not json>'); sys.exit()
try: v=($1)
except Exception as e: v='<err %s>'%e
print(json.dumps(v) if not isinstance(v,str) else v)"; }
expect() { # expect DESCRIPTION ACTUAL EXPECTED
  if [ "$2" == "$3" ]; then ok "$1 (= $3)"; else bad "$1: got '$2', expected '$3'"; fi
}
chat() { # chat SESSION MESSAGE [HEADER]
  local msg; msg="$("$PY" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$2")"
  req POST /chat "{\"session_id\": \"$1\", \"message\": $msg}" "${3:-}"
}

echo "${B}Smoke testing $BASE${N}"

step "GET /health"
req GET /health
expect "status code" "$CODE" 200
expect "status" "$(jget 'j["status"]')" ok
expect "cache_enabled" "$(jget 'j["cache_enabled"]')" true
expect "keys_configured >= 2" "$(jget 'j["keys_configured"] >= 2')" true

SA="smoke-a-$NONCE"; SB="smoke-b-$NONCE"; SC="smoke-c-$NONCE"
MSG="What is the capital of France? Answer in one short sentence. [smoke $NONCE]"

step "POST /chat (live)"
chat "$SA" "$MSG"
expect "status code" "$CODE" 200
expect "session_id echoed" "$(jget 'j["session_id"]')" "$SA"
expect "resolution_source" "$(jget 'j["metadata"]["resolution_source"]')" LIVE_INFERENCE
expect "latency_ms is int" "$(jget 'type(j["metadata"]["latency_ms"]).__name__')" int
expect "input_tokens is int > 0" "$(jget 'type(j["metadata"]["input_tokens"]) is int and j["metadata"]["input_tokens"] > 0')" true
expect "output_tokens is int > 0" "$(jget 'type(j["metadata"]["output_tokens"]) is int and j["metadata"]["output_tokens"] > 0')" true
expect "key_id" "$(jget 'j["metadata"]["key_id"]')" key_1
expect "fallback_attempts" "$(jget 'j["metadata"]["fallback_attempts"]')" 0
LIVE_REPLY="$(jget 'j["reply"]')"; LIVE_MS="$(jget 'j["metadata"]["latency_ms"]')"; LIVE_IN="$(jget 'j["metadata"]["input_tokens"]')"
echo "  reply: ${Y}${LIVE_REPLY:0:100}${N}  (${LIVE_MS} ms, model $(jget 'j["metadata"]["model"]'))"

step "Same message, new session -> LLM_CACHE"
chat "$SB" "$MSG"
expect "status code" "$CODE" 200
expect "resolution_source" "$(jget 'j["metadata"]["resolution_source"]')" LLM_CACHE
expect "identical reply" "$(jget 'j["reply"]')" "$LIVE_REPLY"
expect "key_id is null" "$(jget 'j["metadata"]["key_id"]')" null
expect "fallback_attempts" "$(jget 'j["metadata"]["fallback_attempts"]')" 0
expect "same input_tokens as the stored usage" "$(jget 'j["metadata"]["input_tokens"]')" "$LIVE_IN"
CACHE_MS="$(jget 'j["metadata"]["latency_ms"]')"
if [ "$CACHE_MS" -lt "$LIVE_MS" ]; then ok "cache faster ($CACHE_MS ms < $LIVE_MS ms)"; else bad "cache not faster ($CACHE_MS ms vs $LIVE_MS ms)"; fi

step "Multi-turn memory"
chat "$SA" "Repeat the city you just named, one word only."
expect "status code" "$CODE" 200
echo "  reply: ${Y}$(jget 'j["reply"]' | head -c 100)${N}"
expect "input_tokens grew (history included)" "$(jget "j['metadata']['input_tokens'] > $LIVE_IN")" true

step "Failover: X-Simulate-Failure: key_1=429"
chat "$SC" "Name one primary colour. [smoke $NONCE]" "X-Simulate-Failure: key_1=429"
expect "status code" "$CODE" 200
expect "key_id" "$(jget 'j["metadata"]["key_id"]')" key_2
expect "fallback_attempts" "$(jget 'j["metadata"]["fallback_attempts"]')" 1
expect "real answer (LIVE_INFERENCE)" "$(jget 'j["metadata"]["resolution_source"]')" LIVE_INFERENCE

step "Failover: X-Simulate-Failure: key_1=500"
chat "$SC" "And another one? [smoke $NONCE]" "X-Simulate-Failure: key_1=500"
expect "status code" "$CODE" 200
expect "key_id" "$(jget 'j["metadata"]["key_id"]')" key_2

step "All keys fail -> 503, history unchanged"
req GET "/sessions/$SA/messages"; BEFORE="$(jget 'len(j["messages"])')"
chat "$SA" "This must not be stored" "X-Simulate-Failure: *=429"
expect "*=429 status" "$CODE" 503
expect "*=429 body" "$BODY" '{"detail":"all providers unavailable"}'
chat "$SA" "Neither must this" "X-Simulate-Failure: key_1=429,key_2=500"
expect "key_1=429,key_2=500 status" "$CODE" 503
req GET "/sessions/$SA/messages"; AFTER="$(jget 'len(j["messages"])')"
expect "history length unchanged" "$AFTER" "$BEFORE"

step "GET /sessions/{id}/messages"
req GET "/sessions/$SA/messages"
expect "status code" "$CODE" 200
expect "message count" "$(jget 'len(j["messages"])')" 4
expect "roles" "$(jget '",".join(m["role"] for m in j["messages"])')" "user,assistant,user,assistant"
expect "no system prompt" "$(jget 'any(m["role"]=="system" for m in j["messages"])')" false
expect "assistant metadata present" "$(jget 'all({"resolution_source","input_tokens","output_tokens"} <= set(m.get("metadata",{})) for m in j["messages"] if m["role"]=="assistant")')" true
expect "user has no metadata" "$(jget 'all("metadata" not in m for m in j["messages"] if m["role"]=="user")')" true

step "404 unknown session"
req GET "/sessions/does-not-exist-$NONCE/messages"
expect "status code" "$CODE" 404
expect "body" "$BODY" '{"detail":"session not found"}'

step "422 validation"
req POST /chat '{"session_id": "s-x", "message": ""}';            expect "empty message" "$CODE" 422
req POST /chat '{"session_id": "s-x", "message": "    "}';        expect "whitespace message" "$CODE" 422
LONG="$("$PY" -c 'print("x"*4001)')"
req POST /chat "{\"session_id\": \"s-x\", \"message\": \"$LONG\"}"; expect "4001-char message" "$CODE" 422
req POST /chat '{"message": "hi"}';                               expect "missing session_id" "$CODE" 422
req POST /chat '{"session_id": "s-x", "message": '                ; expect "malformed JSON" "$CODE" 422
expect "422 body has detail" "$(jget '"detail" in j')" true

echo
TOTAL=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then echo "${G}${B}ALL $TOTAL CHECKS PASSED${N}"; else echo "${R}${B}$FAIL of $TOTAL CHECKS FAILED${N}"; fi
exit $(( FAIL > 0 ))
