README
Project

lol-analytics — prototype / MVP for tracking League of Legends player positions (per-second) from a third-party GraphQL websocket feed, storing them, running analyses (e.g. player proximity), and presenting analytical pages for teams / players (mock frontend for commercial stakeholders).

Purpose & Goals

Capture every per-second live frame for active matches (10 players), persist reliably for later analysis.

Provide pre-computed analytics (e.g. jungler–support proximity) to be shown on team/player pages.

Provide a simple prototype that demonstrates value to commercial stakeholders (free / paid tier later).

MVP constraints: 1–5 concurrent matches, retain raw frames 365 days during testing.

Context

Live data source: a third-party GraphQL websocket subscription that streams frames. Each frame includes updated_at and positions for all players.

Static data source: GraphQL static API with teams & players (used to map player IDs, roles).

Auth: GraphQL APIs are authenticated with an API key (provided for testing).

Reliability is critical: lost frames = lost data (no replay guaranteed).

                       +----------------+
                       |  Static GraphQL|  <-- one-off / occasional calls
                       +----------------+
                               |
                               v
  +------------+        +-----------------+       +-----------------+
  |  Extraction|  --->  |   Postgres DB   |  ---> | Analysis Worker |  ---> helper tables (ProximityMinute, etc.)
  | (1 per match)      | (Frames & pos)  |       +-----------------+
  +------------+        +-----------------+
        |                        ^
        v                        |
  Local fallback JSONL           |
  (on DB failure)                |
                                 \
                                  \ 
                                   v
                                 +----------------+
                                 | Django Web App |  (REST + templates - team/player pages)
                                 +----------------+



Components:

Django Web App: REST endpoints + server-rendered mock pages (team & player). No public API required for MVP.

Extraction Worker: 1 process per live match; subscribes to GraphQL websocket, writes Frame + PlayerPosition. Lightweight and highly reliable.

Analysis Worker: post-game (or periodic) batch job to compute helper tables (e.g. ProximityMinute) for fast UI queries.

Database: Postgres (dev: SQLite or Postgres docker). Consider TimescaleDB later for time-series optimizations.

Local fallback: append-only JSONL in worker host when DB is unavailable; replayable via replay_fallback management command.

Monitoring/Alerts: Slack webhook (preferred) or email; logs; consider Sentry / Prometheus later.

Key Non-Functional Requirements

Per-second fidelity: store each frame for each player (10 rows per frame).

Idempotency: unique constraint match, player, updated_at and bulk_create(ignore_conflicts=True) to safely reprocess frames.

Retention: keep raw frames for 365 days while testing; purge via scheduled job.

Reliability: extraction workers must be isolated per match; robust reconnect/backoff + local fallback.

Scale: initially handle 3–5 concurrent matches. Architecture supports horizontal scaling.

Quick start (developer)

Clone repo.

Create .env with required env vars (see IMPLEMENTATION.md).

Start dev DB (recommended: docker-compose up that includes Postgres).

pip install -r requirements.txt

python manage.py migrate

Run static data loader (mock or real) to populate Team & Player.

Run worker pointing to a mocked feed (or test API):
python manage.py run_live_worker --match-id MATCH123

Start web server: python manage.py runserver

Visit /teams/<team_slug>/ to see mock page.