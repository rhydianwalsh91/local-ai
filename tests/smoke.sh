#!/usr/bin/env bash
# Health and speed check for the AI server. Run from your Mac (or anything on the LAN):
#   tests/smoke.sh
# OLLAMA_URL=http://host:11434 tests/smoke.sh   to point it somewhere else.
#
# Loads the models if they aren't already, so a cold run takes ~1-2 minutes.
# Exits non-zero if anything is broken or clearly too slow.
set -euo pipefail

URL="${OLLAMA_URL:-http://192.168.68.158:11434}"
CHAT_MODEL="${CHAT_MODEL:-gemma4-cpu}"
DECIDE_MODEL="${DECIDE_MODEL:-tev1:4b}"
MIN_GEN_TPS="${MIN_GEN_TPS:-3.5}"   # expect ~6; ~2.5 means speculative decoding is back on

fail=0
ok()   { printf '  \033[32mOK\033[0m    %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; fail=1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }

echo "Server: $URL"

if ! version=$(curl -fsS -m 10 "$URL/api/version" | json 'print(d["version"])'); then
  bad "can't reach Ollama. Is the mini PC on? Try: ssh minipc-ai systemctl status ollama"
  exit 1
fi
ok "Ollama $version is up"

tags=$(curl -fsS -m 10 "$URL/api/tags")
for model in "$CHAT_MODEL" "$DECIDE_MODEL"; do
  if echo "$tags" | json "sys.exit(0 if any(m['name'] in ('$model', '$model:latest') for m in d['models']) else 1)"; then
    ok "model $model is installed"
  else
    bad "model $model is missing (run scripts/deploy.sh)"
  fi
done

echo "Chat ($CHAT_MODEL)..."
start=$(date +%s)
if reply=$(curl -fsS -m 400 "$URL/api/chat" -d "{
    \"model\": \"$CHAT_MODEL\", \"stream\": false, \"think\": false,
    \"messages\": [{\"role\": \"user\", \"content\": \"Write two sentences about the sea.\"}],
    \"options\": {\"num_predict\": 64}}"); then
  echo "$reply" | json "
s = lambda ns: ns / 1e9
load, pe, pn, ev, en = s(d.get('load_duration', 0)), s(d['prompt_eval_duration']), d['prompt_eval_count'], s(d['eval_duration']), d['eval_count']
print(f'  load {load:.1f}s | prompt {pn} tok at {pn/pe:.1f} tok/s | output {en} tok at {en/ev:.1f} tok/s | total $(( $(date +%s) - start ))s')
print(f'  reply: {d[\"message\"][\"content\"][:100]!r}')
sys.exit(0 if en / ev >= $MIN_GEN_TPS else 3)
" && ok "chat works" || bad "chat output slower than $MIN_GEN_TPS tok/s (check draft_num_predict in the Modelfile)"
else
  bad "chat request failed"
fi

echo "Decision ($DECIDE_MODEL via /v1/systemone)..."
start=$(date +%s)
if answer=$(curl -fsS -m 200 "$URL/v1/systemone" -d "{
    \"model\": \"$DECIDE_MODEL\",
    \"state\": \"My parcel still hasn't arrived and nobody answers my emails.\",
    \"questions\": {
      \"is_complaint\": {\"type\": \"noul\", \"instructions\": \"Is the customer unhappy?\",
        \"criteria\": {\"true\": \"Expresses a problem.\", \"false\": \"Neutral or happy.\"}},
      \"is_about_billing\": {\"type\": \"noul\", \"instructions\": \"Is this about payment or refunds?\"}}}"); then
  took=$(( $(date +%s) - start ))
  if echo "$answer" | json "
a = d['answers']
print(f'  is_complaint={a[\"is_complaint\"][\"noul\"]:.2f} is_about_billing={a[\"is_about_billing\"][\"noul\"]:.2f} | ${took}s')
sys.exit(0 if a['is_complaint']['noul'] > 0.5 > a['is_about_billing']['noul'] else 3)
"; then ok "decision works"; else bad "decision answers look wrong: $answer"; fi
else
  bad "decision request failed"
fi

WEBUI_URL="${WEBUI_URL:-${URL%:*}:8080}"
if curl -fsS -m 10 "$WEBUI_URL/health" >/dev/null 2>&1; then
  ok "Open WebUI is up at $WEBUI_URL ($(curl -fsS -m 10 "$WEBUI_URL/api/version" | json 'print(d["version"])' 2>/dev/null || echo "version unknown"))"
else
  bad "Open WebUI isn't answering at $WEBUI_URL (try: ssh minipc-ai docker logs --tail 50 open-webui)"
fi

echo "Loaded now:"
curl -fsS -m 10 "$URL/api/ps" | json "
for m in d['models']: print(f'  {m[\"name\"]:<20} {m[\"size\"]/1e9:5.1f} GB  until {m[\"expires_at\"][:19]}')"

[ "$fail" -eq 0 ] && echo "All good." || { echo "Some checks failed."; exit 1; }
