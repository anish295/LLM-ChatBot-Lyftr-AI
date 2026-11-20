# Demo video script (2:30 - 2:50)

**Before recording**
- Wake the backend: open `https://<backend>/health` about a minute before you start, since free Render may be asleep.
- Open three tabs: the **frontend URL**, **`<backend>/docs`**, and the **GitHub repo**. Keep a terminal ready with `B=https://<backend>` exported.
- Use a short, fresh question you haven't asked before (cached answers persist), e.g. *"What is the tallest mountain in Africa?"*
- Desktop width, so the Tools panel is open. Zoom the browser to about 110% for readability.

---

### 0:00 - 0:15 · Intro
> "Hi, I'm *<name>*. This is my submission for Lyftr AI: an LLM chatbot with API-key failover and response caching. React frontend, FastAPI backend, LiteLLM as the gateway, SQLite for storage, all deployed on free tiers. Here's the live app."

*Show the frontend. Point at the header pill: "Online · 2 keys · cache on".*

### 0:15 - 0:40 · Live inference and metadata
*Type: "What is the tallest mountain in Africa?" and press Enter.*
> "Every reply shows that request's metadata. The source is **LIVE_INFERENCE**, the model is Groq's gpt-oss-120b, latency is in milliseconds, and these are the input and output tokens for this request only, never a conversation total. It was answered by key_1 with zero fallbacks."

### 0:40 - 1:00 · Cache hit
*Reload the page (point out that the session id in the header changes), then send the exact same question.*
> "Reloading starts a brand-new session. Same question: now it's **LLM_CACHE**. The reply is identical, it took a couple of milliseconds instead of hundreds, the token usage is the stored usage, and key_id is null because no provider was called. The cache key is the model plus the full message list."

### 1:00 - 1:20 · Multi-turn memory and system prompt
*Send: "And how tall is it?" and the bot answers with Kilimanjaro's height.*
> "It remembers the conversation: history is stored per session in SQLite and rebuilt every turn."

*Click New chat. In Tools, click the **Pirate** system-prompt preset and send "Describe the sea in one sentence."*
> "There's also an optional system prompt per session."

### 1:20 - 1:50 · Failover with X-Simulate-Failure
*In Tools → Failure simulator, click **key_1 = 429**. Point at the header preview. Send "Name one planet."*
> "Now I make key_1 return HTTP 429 for this one request using the X-Simulate-Failure header. The app fails over automatically: **key_2** answered with a real live answer, fallback_attempts is 1, and this chip shows key_1 → key_2. Simulated requests skip the cache read so you always see the real failover path."

*Click **\* = 429** and send "Name another planet."*
> "If every key fails, the user gets a clean, readable message and a retry button, never a broken screen. The API returns a 503 with `all providers unavailable`, and nothing is written to history."

### 1:50 - 2:25 · Endpoints (Swagger + curl)
*Switch to `/docs`.*
> "The backend exposes exactly three endpoints."

*In the terminal, run each command and point at the result:*
```bash
curl -s $B/health
curl -s -X POST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=500' -d '{"session_id":"demo","message":"Say hi"}'
curl -s $B/sessions/demo/messages
curl -s -i $B/sessions/unknown/messages | head -1      # 404 session not found
curl -s -i -X POST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"demo","message":"   "}' | head -1   # 422
```
> "Health reports the key pool and cache. key_1=500 also fails over to key_2. The history endpoint returns the conversation oldest first, without the system prompt. An unknown session is a 404 and a whitespace-only message is a 422, all as JSON."

*(Optional, if time allows: `bash scripts/smoke_test.sh $B` and show "ALL 45 CHECKS PASSED".)*

### 2:25 - 2:50 · Repo tour and wrap-up
*Switch to GitHub. Scroll the README headings, then show `docker-compose.yml`, `Makefile` and `backend/app/llm_gateway.py`.*
> "Locally, everything starts with `make up`: multi-stage Docker images and a named volume at /data, so history and the disk cache survive restarts. The README covers the design decisions and a verification guide. There are 103 backend tests plus Playwright UI tests in CI. Thanks for watching!"
