# Pairza

**One stranger. One mystery. One day.**

Every 24 hours, Pairza randomly pairs a user with one other person, somewhere in the world, and gives each of them
half the clues to a mystery. Neither can solve it alone. The connection expires in 24 hours whether they solve it
or not.

This is a real, working full-stack implementation — not a mockup. Real PostgreSQL, real Redis, real WebSocket chat,
a real matchmaking engine with an automated test suite, and a real Next.js frontend, all wired together.

## What's actually implemented

**Backend (FastAPI + PostgreSQL + Redis) — fully functional:**
- Email/password auth (Argon2id hashing, JWT access + refresh token rotation, httpOnly cookies). Google OAuth has a
  complete, working implementation but needs your own Google OAuth credentials to activate (see below).
- The matchmaking engine: Redis-locked pairing, permanent block exclusion, a time-based cooldown before the same two
  people can be re-paired, a time-based cooldown before the same person sees the same mystery again, and randomized
  clue-role assignment. **This is the part the product lives or dies on, and it has direct test coverage** proving
  two matched users always get the same mystery with genuinely different, complementary clues.
- The mystery engine: multi-stage mysteries with per-stage checkpoint answers and a final answer, each stage holding
  two different clues (`player_a` / `player_b`) that are never both shown to the same person.
- Session lifecycle with **backend-authoritative expiry** — a background sweeper plus lazy-check-on-access, so a
  client can never submit a correct answer after time is up, and a manipulated client clock can't extend anything.
- Real-time chat over WebSockets: presence, typing indicators, distinct system/discovery/normal message types, a
  short-lived single-use ticket auth scheme (so the long-lived access token, correctly httpOnly, never has to be
  exposed to JS or put in a URL).
- Rewards: XP with speed and streak bonuses, badge criteria checking, a Memory Vault entry written for both
  participants on every completed session.
- Moderation: blocking a partner **immediately ends the active session** for both people (tested); reporting alone
  does not (an admin reviews it instead).
- Admin: user suspend/ban, mystery CRUD + publish workflow, report review queue, and an analytics endpoint.
- **27 passing automated tests** against a real Postgres + Redis instance (see `apps/api/tests/`) covering every
  invariant above, not mocks.

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
- **Google OAuth**: the verification logic, endpoint, and frontend integration point are complete and correct, but
  untestable in this environment without real Google credentials (see `GOOGLE_CLIENT_ID` below).
- **Admin analytics**: one real chart (completions by category) plus the core KPIs, rather than an exhaustive
  dashboard.
- **Creator/UGC system**: intentionally not built — the spec itself flags this as post-MVP.
- **Frontend automated tests**: the backend has full test coverage; the frontend was verified via a real production
  build + manual end-to-end smoke testing (login, matchmaking, chat, all working through the actual proxy/cookie
  architecture), but doesn't yet have a Vitest/Playwright suite.
- **"One mystery per calendar day"**: there's no hard midnight reset. The 24-hour session window *is* the pacing
  mechanism — once your session ends, you're free to look for the next one immediately. This felt truer to the
  product than adding artificial calendar-day gating the spec didn't fully define.

None of this is hidden inside the code — search for scope-decision comments if you want the reasoning inline.

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

**Demo login:** `demo@pairza.app` / `PairzaDemo123!`
**Admin login:** `admin@pairza.app` / `PairzaAdmin123!`

### Testing matchmaking yourself

Matchmaking needs two different accounts online at once — open a second browser profile or an incognito window and
log in as one of the seeded accounts (`seed_user_0@pairza.app` through `seed_user_25@pairza.app`, all with password
`SeedPassword123!`), then hit "Enter today's mystery" on both. You should get paired within a couple of seconds.

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
│   │   ├── scripts/seed.py      # demo data
│   │   └── tests/               # 27 tests, real Postgres + Redis
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
