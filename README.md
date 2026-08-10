# ✨ EnchantmentBet

Statistical sports prediction platform covering **football, basketball and
tennis**. Pulls the latest fixtures, team form, injuries and team news, runs
them through a per-sport statistical model ensemble, and serves date-organized
predictions to a Next.js dashboard.

| Layer | Stack |
|---|---|
| Frontend | Next.js 14 (App Router, TypeScript, Tailwind) + TanStack React Query |
| Backend | FastAPI (async, Python 3.12+) |
| Database | MongoDB (via Motor), predictions keyed by `(sport, date, fixture_id)` |
| Data | api-sports.io (football + basketball), api-tennis.com, newsapi.org — with a built-in deterministic mock mode |

## Quick start

```bash
# 1. MongoDB
docker compose up -d mongo

# 2. Backend (http://localhost:8000, docs at /docs)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env           # add API keys here when you have them
.venv/bin/uvicorn app.main:app --reload

# 3. Frontend (http://localhost:3000)
cd ../frontend
npm install
npm run dev
```

Open http://localhost:3000, pick a date and press **Refresh predictions**.
With no API keys configured the app runs in **mock mode** — a deterministic,
realistic sample slate per date — so everything works out of the box. Add keys
to `backend/.env` to switch to live data (`DATA_MODE=auto` picks live
automatically per sport once its key is present):

- `APISPORTS_KEY` — [api-sports.io](https://api-sports.io) (covers API-FOOTBALL and API-BASKETBALL)
- `APITENNIS_KEY` — [api-tennis.com](https://api-tennis.com)
- `NEWSAPI_KEY` — [newsapi.org](https://newsapi.org) (optional; enriches predictions with headline sentiment)

## How predictions work

Each sport has a dedicated statistical model, blended with an Elo-style team
rating, recent form, head-to-head record, injuries, and news sentiment
(`backend/app/engine/`):

- **Football — Dixon-Coles adjusted Poisson.** Attack/defence rates relative
  to league average produce expected goals for each side; a full scoreline
  probability matrix (with the Dixon-Coles low-score correlation fix) yields
  1X2, over/under 2.5, BTTS and the most likely score.
- **Basketball — pace-adjusted efficiency.** Offensive/defensive ratings
  scaled by opponent and blended pace give expected points; the margin is
  modeled as a normal distribution (σ ≈ 11.5) for win probability, spread and
  total.
- **Tennis — serve-model Markov chain.** Serve/return point-win rates walk a
  memoized point → game → tiebreak → set → match recursion, giving match win
  probability and the set-score distribution.

On top of the base model, the ensemble (`engine/ensemble.py`) applies:

- **Elo blend** — model probability is mixed ~60/40 with the rating
  expectation (ratings derived from season performance when no maintained Elo
  exists).
- **Injuries** — each missing player subtracts strength proportional to
  importance and status (out/doubtful/questionable), capped at 18%; it also
  depresses the effective rating.
- **News sentiment** — keyword-scored headlines nudge team strength by at most
  ±3%, never more.
- **Form & H2H** — recency-weighted last-5 form and the head-to-head record
  shift the win-probability split by a few points at most.
- **Confidence** — distance between the top two outcomes, discounted by data
  completeness, labeled low/medium/high.

Every factor that moved a prediction is surfaced on the card, so a pick is
always explainable.

## Date-scoped storage & refresh

Predictions live in MongoDB keyed by `(sport, date, fixture_id)` with a unique
index. **Refreshing a date deletes and regenerates only that date's
documents** — other dates are never touched. The frontend mirrors this:
React Query caches per `['predictions', date, sport]` and a refresh
invalidates only that date's keys. `refresh_meta` tracks when each
(sport, date) slate was last generated and from which source (live/mock).

## API

- `GET /api/predictions?date=YYYY-MM-DD[&sport=football|basketball|tennis]` —
  read stored predictions for a date.
- `POST /api/predictions/refresh` with `{"date": "YYYY-MM-DD", "sport": null}` —
  re-pull fixtures/stats/injuries/news and regenerate that date (one sport, or
  all when `sport` is null).
- `GET /api/health` — liveness.

## Project layout

```
backend/
  app/
    engine/       # Dixon-Coles, basketball, tennis Markov, Elo, ensemble
    providers/    # mock + api-sports + api-tennis + news adapters
    routers/      # FastAPI endpoints
    services/     # date-scoped refresh orchestration
    schemas.py    # shared pydantic models
frontend/
  app/            # Next.js App Router pages
  components/     # dashboard UI (cards, outcome bars, tabs, date nav)
  hooks/          # React Query hooks (date-scoped cache keys)
  lib/            # API client + types
```

## A note on "best"

No model predicts sport with certainty — this engine is built on the same
families of models the quantitative betting literature uses (Dixon-Coles,
efficiency ratings, serve-hold Markov chains), tuned to be honest: calibrated
probabilities, capped adjustment factors, and explicit confidence labels.
Treat outputs as probabilities, not promises, and bet responsibly.
