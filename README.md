# Pairza

**One stranger. One mystery. One chance.**

Pairza randomly pairs a user with one other person, somewhere in the world, and gives each of them half the clues
to a mystery. Neither can solve it alone. The clock starts the moment they're paired, and the connection expires
when it runs out — whether they've solved it or not. How long they get depends on how hard the mystery is:

| Difficulty | Time limit | Challenge style             |
| ---------: | ---------: | --------------------------- |
|          1 |  5 minutes | Straightforward clues       |
|          2 | 10 minutes | Requires discussion         |
|          3 | 15 minutes | Multiple connected clues    |
|          4 | 20 minutes | Misleading / indirect clues |
|          5 | 30 minutes | Complex deduction           |

These numbers live in exactly one place — [`apps/api/app/mysteries/difficulty.py`](apps/api/app/mysteries/difficulty.py) —
see [Difficulty & time limits](#difficulty--time-limits) below.

This is a real, working full-stack implementation — not a mockup. Real PostgreSQL, real Redis, real WebSocket chat,
a real matchmaking engine with an automated test suite, and a real Next.js frontend, all wired together.

## What's actually implemented

**Backend (FastAPI + PostgreSQL + Redis) — fully functional:**
- Email/password auth (Argon2id hashing, JWT access + refresh token rotation, httpOnly cookies). Google sign-in is
  implemented on the API (`POST /api/auth/google`); the web app has no Google button yet, and it needs your own Google
  OAuth credentials to activate (see below).
- The matchmaking engine: Redis-locked pairing, permanent block exclusion, a time-based cooldown before the same two
  people can be re-paired, a time-based cooldown before the same person sees the same mystery again, and randomized
  clue-role assignment. **This is the part the product lives or dies on, and it has direct test coverage** proving
  two matched users always get the same mystery with genuinely different, complementary clues.
- The mystery engine: multi-stage mysteries with per-stage checkpoint answers and a final answer, each stage holding
  two different clues (`player_a` / `player_b`) that are never both shown to the same person.
- Session lifecycle with **backend-authoritative expiry** — a background sweeper plus lazy-check-on-access (and a
  re-check under the row lock on every answer, plus on every WebSocket chat message), so a client can never submit
  a correct answer or send a message after time is up, and a manipulated client clock can't extend anything.
- Real-time chat over WebSockets: presence, typing indicators, distinct system/discovery/normal message types, a
  short-lived single-use ticket auth scheme (so the long-lived access token, correctly httpOnly, never has to be
  exposed to JS or put in a URL).
- Rewards: XP with speed and streak bonuses, badge criteria checking, a Memory Vault entry written for both
  participants on every completed session.
- Moderation: blocking a partner **immediately ends the active session** for both people (tested); reporting alone
  does not (an admin reviews it instead).
- Admin: user suspend/ban, mystery CRUD + publish workflow, report review queue, category enable/disable, a
  real AI-backed mystery generation pipeline (see below), and an analytics endpoint (DAU/MAU/retention, matches
  and completions per user, average session length).
- **85 automated test functions** written against a real Postgres + Redis instance (see `apps/api/tests/`)
  covering every invariant above, not mocks. Run them with `pytest -v` from `apps/api`.

**Frontend (Next.js 16 + React 19 + Tailwind v4) — fully functional:**
- Landing page, auth, the daily home screen, the cinematic mystery-reveal sequence, the investigation workspace
  (3-pane desktop / tabbed mobile) with live chat, evidence board, countdown, and answer submission, the achievement
  -focused Memory Vault and profile, and a working admin dashboard.
- A custom, non-generic design system (see `apps/web/app/globals.css`) rather than default framework styling.
- A real ambient 3D globe (react-three-fiber) on the landing page.
- The production build (`npm run build`) passes clean, including full TypeScript type-checking.

## What's intentionally scoped down for this pass

The full spec describes a venture-scale product. Rather than half-build everything, this pass makes the **core loop**
completely real, with the architecture built to extend cleanly:

- **Mystery content**: 8 hand-authored mysteries across 5 of the 9 categories (the extensible schema already
  supports all 9 — adding a category is a one-line addition plus content, no code changes to matchmaking, sessions,
  or chat). `apps/api/scripts/seed.py` is where to add more.
- **Google OAuth**: the API side (token verification, the endpoint, and the account-matching rules below) is
  complete, but there is no Google button in the web app yet, and it's untestable in this environment without real
  Google credentials (see `GOOGLE_CLIENT_ID` below).
- **Admin analytics**: one real chart (completions by category) plus the core KPIs, rather than an exhaustive
  dashboard.
- **Creator/UGC system**: intentionally not built — the spec itself flags this as post-MVP.
- **Frontend automated tests**: the backend has full test coverage; the frontend was verified via a real production
  build + manual end-to-end smoke testing (login, matchmaking, chat, all working through the actual proxy/cookie
  architecture), but doesn't yet have a Vitest/Playwright suite. The exceptions are the countdown's timing math and
  the game-audio engine, which live in dependency-free modules with their own `node --test` suites (`npm test` in
  `apps/web`, Node 22.6+).
- **"One mystery per calendar day"**: there's no hard midnight reset and no daily cap. Once your session ends
  (solved, or its time limit runs out), you're free to look for the next one immediately; the match and mystery
  cooldowns are what keep repeats away. This felt truer to the product than adding artificial calendar-day gating
  the spec didn't fully define.
- **AI mystery generation**: the full three-stage pipeline (structural → duplicate → semantic validation) is real
  and tested, but two things inside it are deliberately simpler than a production version might warrant —
  duplicate detection is exact-normalized-text matching, not embedding-based semantic similarity (would catch
  "the same mystery, reworded" today; won't catch "conceptually the same mystery with entirely different wording");
  and there's no per-draft manual review screen (drafts either auto-publish or wait for an admin to flip a single
  status, rather than a browse-and-approve-one-by-one UI). Both are called out as reasonable initial cuts;
  extending either doesn't require touching matchmaking, sessions, or the validation pipeline's structure.

None of this is hidden inside the code — search for scope-decision comments if you want the reasoning inline.

## Difficulty & time limits

A mystery's `difficulty` (1–5) decides how long a pair has to solve it — see the table at the top. The single source
of truth is `apps/api/app/mysteries/difficulty.py`; **to change a duration, edit `_TIERS` there and nothing else.**
Everything below reads from it instead of restating the numbers:

- **Session start** — matchmaking sets `expires_at = started_at + time_limit(mystery.difficulty)` once, when the
  session is created. It is stored, never recomputed, so it can't drift and a page refresh can't reset it.
- **API** — `GET /api/sessions/{id}` returns `expires_at`, `duration_seconds`, `expiring_warning_seconds` and
  `server_time`; mysteries carry `time_limit_seconds`; `GET /api/mysteries/difficulty-levels` returns the whole table.
- **Frontend** — the countdown never keeps its own duration. It counts down to the server's `expires_at`, using
  `server_time` to correct for the device clock, so both players see the same remaining time (to within network
  latency) and a wrong device clock can't skew it. At zero the workspace locks immediately and re-syncs with the server.
- **Enforcement** — answers, evidence and chat are all refused once the deadline passes, and the session moves to
  `EXPIRED` through the existing timeout path (no XP, streak breaks, history + Memory Vault entries).
- **Validation** — every schema that accepts a difficulty (`MysteryCreate`, `MysteryUpdate`, the AI candidate, the
  generate request) uses the same `MIN_DIFFICULTY`/`MAX_DIFFICULTY`. The AI generator and its semantic reviewer are
  told the time limit, so they aim for puzzles that are solvable in it.
- **"Expiring soon"** — fires when the last fifth of a session's own time is left (1 min of 5, 6 min of 30).

Sessions that were already in progress when this shipped keep the end time they were created with (up to 24 hours)
and finish normally; no data migration is involved.

## Game audio

Sound is handled by one reusable audio manager in `apps/web/lib/audio/`; nothing else in the app creates audio.

- **Assets** live in `apps/web/public/audio/` and are served from `/audio/…`. Today that is just
  `investigation_ambient_01.ogg`, the looping background ambience.
- **When it plays** — app-wide, as one continuous track: it starts on the landing page (`/`) and keeps playing through
  login, home and the investigation screen, without restarting when the player navigates. `AmbienceController` is
  mounted once in the root layout, so only a full page reload restarts it. Browsers don't allow sound before the
  visitor has interacted, so on a cold page load it begins at the first click, tap or key press.
- **Volume** — master volume, music/ambience volume and mute live in `stores/use-audio-store.ts` and are saved per
  device in `localStorage` (`pairza_audio_settings_v1`). The default ambience level is deliberately low. A small
  mute button floats in the bottom-left corner of every page; the volume sliders are a future settings screen's job.
- **Adding a sound** — drop the file into `public/audio/`, add one entry to `lib/audio/sounds.ts`, then call
  `audioManager.play("<id>")` (`import { audioManager } from "@/lib/audio"`). Looping sounds keep a single instance;
  one-shot effects may overlap. A missing or undecodable file never breaks the game: it logs one console warning and
  stays silent.
- **Browsers** — audio can't start until the player has interacted with the page, so the manager waits for the first
  click/tap/keypress when it has to. Ogg Vorbis isn't decodable everywhere (notably older Safari); `sources` in
  `sounds.ts` takes a fallback format (`.m4a` / `.mp3`) when one is needed.

## Quick start (Docker — recommended)

Requires Docker and Docker Compose.

```bash
cp .env.example .env          # defaults work fine for local dev
docker compose up --build
```

Then, once it's up, seed the database (safe to re-run — it skips anything that already exists):

```bash
docker compose exec api python -m scripts.seed
```

- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs

## Quick start (without Docker)

You'll need Python 3.12+, Node 20+, PostgreSQL 16, and Redis running locally.

```bash
# Backend
cd apps/api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL/REDIS_URL if yours differ
createdb pairza
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

## Running the test suite

```bash
cd apps/api
createdb pairza_test   # one-time; tests manage their own schema after that
source venv/bin/activate
pytest -v
```

Tests hit a real Postgres (`pairza_test`) and a real Redis (`db 1`, isolated from your dev data) — nothing here is
mocked. See `apps/api/tests/conftest.py` for how isolation between tests works.

## Enabling Google OAuth

1. Create an OAuth 2.0 Client ID at https://console.cloud.google.com/apis/credentials (type: Web application).
2. Add `http://localhost:3000` as an authorized JavaScript origin.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in your `.env`, then restart.

Without these set, `POST /api/auth/google` returns a clear "not configured" error rather than failing silently —
email/password auth is completely unaffected either way.

### How a Google sign-in is matched to an account

Google's `email_verified` claim is required: a token whose email Google hasn't verified is refused
(`401 google_email_unverified`). After that:

| Situation | Result |
| --- | --- |
| The Google account is already linked to a Pairza account | Signs in. |
| No Pairza account uses that email | Creates one (the client must send a `username` and `country_code`, else `401 google_needs_profile`). |
| An account uses that email and is **verified**, with no Google link | Links to it. |
| An account uses that email but is **unverified** (every password sign-up today) | **Refused**, `409 google_email_in_use`; nothing is changed and no session is issued. |
| An account uses that email but is linked to a *different* Google account | Refused, `409 google_email_in_use`; never overwritten. |

The refusal in the fourth row is deliberate. Password sign-up doesn't prove the person owns the email, so if
Google matched by email alone, someone could register a victim's address with their own password and then hand the
victim's later Google sign-in an account the attacker still controls (account pre-hijacking). Until email
verification exists, a person who signed up with a password keeps using that password. Safe linking for them (a
signed-in "connect Google" action, plus email verification so unverified accounts can be reclaimed) is future work.

## AI mystery generation

Beyond the hand-authored seed mysteries, Pairza can generate new ones with a real AI pipeline: generation →
structural validation → duplicate detection → semantic review → save. Nothing here runs during live gameplay —
it's strictly an offline/admin tool, either from the command line or the admin panel's **Mysteries** tab.

**Setup:** get an API key at https://console.anthropic.com, then add it to your `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Leave it blank to skip this feature entirely — everything else in the app works fine without it.

**From the command line:**
```bash
docker compose exec api python -m scripts.generate_mysteries --category geo --quantity 5
docker compose exec api python -m scripts.generate_mysteries --all-categories --quantity 3
docker compose exec api python -m scripts.generate_mysteries --category cipher --quantity 2 --dry-run
```
`--dry-run` generates and validates without saving anything — good for a first test before spending real API calls
on a full batch. The report at the end shows exactly what was requested, attempted, rejected (with the specific
reason), and saved, per category.

**From the admin panel:** the Mysteries tab shows every category's published/draft counts with an enable/disable
toggle (disabled categories are immediately excluded from matchmaking — see
`apps/api/tests/test_mystery_selection.py` for the enforcement tests), plus a "Generate more" control that runs
the same pipeline as a background job and polls for progress.

**Validating a single candidate directly** (useful when iterating on the generation prompt):
```bash
docker compose exec api python -m scripts.validate_mystery path/to/candidate.json
```

By default, anything that passes every validation stage publishes immediately (`MYSTERY_AUTO_PUBLISH=true`). Set
it to `false` in your `.env` if you'd rather validated mysteries wait for an admin to manually publish each one.

## Project structure

```
pairza/
├── docker-compose.yml
├── apps/
│   ├── api/                     # FastAPI backend
│   │   ├── app/
│   │   │   ├── auth/            # register, login, JWT, Google OAuth
│   │   │   ├── users/           # profiles, preferences
│   │   │   ├── matchmaking/     # the pairing engine
│   │   │   ├── mysteries/       # mystery/stage/clue model + answer matching
│   │   │   ├── sessions/        # investigation workspace, expiry authority
│   │   │   ├── chat/            # message persistence
│   │   │   ├── websockets/      # connection manager + WS endpoint
│   │   │   ├── rewards/         # XP, badges, memories
│   │   │   ├── moderation/      # blocks, reports
│   │   │   ├── admin/           # moderation + mystery CRUD + analytics
│   │   │   └── common/          # db, redis, security, shared deps
│   │   ├── alembic/             # migrations
│   │   ├── scripts/             # seed.py (demo data), generate_mysteries.py + validate_mystery.py (AI pipeline)
│   │   └── tests/               # 85 test functions, real Postgres + Redis
│   └── web/                     # Next.js frontend
│       ├── app/                 # routes (landing, auth, home, mystery, vault, profile, admin)
│       ├── components/          # UI primitives + feature components
│       ├── features/            # TanStack Query hooks per domain
│       ├── lib/                 # API client, WebSocket hook, utils
│       └── stores/               # Zustand stores
```

## A note on the matchmaking invariant

The single most load-bearing piece of this product is: **two randomly matched strangers must always get
complementary (not identical) clues on the same mystery, and the backend must be the sole authority on everything
that matters (pairing, session state, expiry, answer correctness).** Every other feature is built around protecting
that guarantee. If you only read one test file, read
`apps/api/tests/test_matchmaking.py::test_two_matched_users_get_same_mystery_but_different_clues`.
