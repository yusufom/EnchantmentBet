# ✨ EnchantmentBet

Statistical sports prediction platform, currently focused on **football**
(the engine also supports basketball and tennis — re-enable via
`ENABLED_SPORTS` in `backend/.env`). Pulls the latest fixtures, team form,
injuries and team news, runs them through a statistical model ensemble, and
serves date-organized predictions to a Next.js dashboard.

Football coverage: the top European leagues **and their second divisions**
(La Liga/Segunda, Serie A/B, Bundesliga/2. Bundesliga, Ligue 1/2, Eredivisie,
Primeira Liga, Scottish Premiership…), the **full EFL ladder** (Premier
League, Championship, League One, League Two + FA Cup and League Cup),
continental cups, and other majors — in priority order, capped by
`MAX_FIXTURES`.

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
- `ANTHROPIC_API_KEY` — [Anthropic](https://console.anthropic.com) (optional; enables the Claude review layer)

### Expected goals (xG)

Team strength for the big-5 leagues (Premier League, La Liga, Serie A,
Bundesliga, Ligue 1) is driven by **expected goals** rather than actual ones.
A scoreline contains a lot of finishing luck that does not repeat; xG measures
the chances a team created and conceded, which does. Both the Dixon-Coles
scoring rates and the Elo rating use a blend, set by `XG_WEIGHT` (default
`0.7`; `0` turns the layer off).

Measured on a walk-forward backtest of **1,462 out-of-sample big-5 fixtures**
from 2024/25 — team strength rebuilt from only the matches played before each
fixture, then run through the real prediction code:

| | actual goals | xG blend (0.7) |
|---|---|---|
| Pick accuracy | 51.50% | **53.69%** (+2.19 pts) |
| Log-loss | 1.0012 | **0.9841** |
| Brier score | 0.5968 | **0.5857** |

A paired McNemar test gives p = 0.0017, so the gain is statistically real
rather than noise. Cards backed by xG are labelled `+ xg` in the algorithm
field, and a team scoring well above or below its chances is called out as a
factor.

Source is Understat's own league endpoint, cached for 24h in process and
persisted with the team stats. Clubs are matched to api-sports ids by
normalised name with a small alias table — verified at 96/96 across the big
five. Leagues Understat does not cover (the EFL, most of the world) keep using
actual goals automatically.

### Bookmaker odds & match facts (SportMonks)

With `SPORTMONKS_API_KEY` set, covered fixtures gain a **market view** and a
set of **match facts**.

De-vigged 1X2, over/under 2.5 and both-teams-to-score probabilities are
blended into the model's own at `ODDS_WEIGHT` (default `0.5`). Backtested
walk-forward on 157 Danish/Scottish fixtures with historical pre-match odds:

| | model alone | +market (0.5) | market alone |
|---|---|---|---|
| Log-loss | 1.0264 | 1.0068 | 1.0008 |
| Brier | 0.6141 | 0.6013 | 0.5975 |
| Pick accuracy | 49.04% | 51.59% | 49.04% |

Blending improves **calibration** monotonically; it does **not** reliably
improve which side is picked (McNemar p = 0.82 — the favourite is usually the
same either way). So odds are used to sharpen the probabilities, not to pick
winners, and the weight stops well short of 1.0 because a full blend would
simply reproduce the bookmaker's book. Sample is small (157) — treat as
provisional.

**Match facts** are shown on the card and passed to Claude: the market's
favourite, venue and capacity, weather, referee, absentees, head-to-head
record, and — most usefully — a flag when the model and the market disagree
by more than 8 points, which is either an edge or a sign the model is missing
something.

*Plan limits, verified by probing this key:* the free tier covers only the
**Danish Superliga** and **Scottish Premiership**; fixtures, pre-match odds,
statistics, lineups, events, sidelined players, weather, venues, referees,
standings and head-to-head are available, while predictions/probabilities,
value bets, xG, trends and the news feed return 403. Uncovered leagues fall
through untouched. Fixture matching is orientation-aware — a reversed
home/away pairing is the other leg and is rejected rather than matched, which
would otherwise invert the odds.

### Claude review layer

With `ANTHROPIC_API_KEY` set, every refreshed prediction is reviewed by Claude
(`LLM_MODEL`, default `claude-opus-5`). For each fixture Claude:

- **filters the news** — keyword search inevitably attaches articles about
  other clubs; Claude keeps only items genuinely about the two teams,
- **writes a short analysis** shown on the card,
- **applies a small bounded adjustment** (max ±7 points of win probability)
  when the headlines/injuries contain something the statistical model missed,
- **makes its own independent picks**, shown as "✦ Claude's prediction" on
  the card: full-time winner (1/X/2), double chance (1X/12/X2), over/under
  1.5 and 2.5 goals, both-teams-to-score and first-half leader for football;
  winner, first-half leader and total points vs the model's line for
  basketball. These are graded against results just like the model's picks
  (first-half markets use real half-time scores), and the day summary shows
  a separate Claude accuracy row — so you can see over time whether the AI
  or the statistical model calls more games right.

The statistical model remains the backbone — Claude can nudge, never
override — and any API failure falls back to the untouched statistical
prediction. Reviewing a 40-fixture slate costs roughly $0.20–0.40 per refresh
at Opus pricing; set `LLM_ENABLED=false` to switch the layer off without
removing the key.

### Results & accuracy

`POST /api/results/refresh {"date": ...}` (or the **Update results** button)
fetches final scores for the date's fixtures and grades every prediction:
main pick, over/under 2.5, both-teams-to-score, and exact scoreline. Graded
cards show the final score and a hit/miss badge, and the dashboard shows the
day's accuracy summary (picks %, per-market %, exact-score %). Run it at the
end of the day — on free api-sports plans, fixture data is only accessible
within about a day of today, so grade a slate the same evening or the next
morning.

**Free-plan note (api-sports):** free keys allow only ~100 requests/day and
10/minute, and expose stats a couple of seasons back. The provider is built
around that:

- **Team strength comes from league standings, not per-team lookups.** One
  `/standings` call returns every club in a competition with played, W/D/L,
  goals for/against and form — so a 40-fixture slate costs ~9 requests
  instead of ~120, and nearly every team gets real numbers.
- **Stats persist in MongoDB** (`stats_ttl_days`, default 7), so restarts and
  next-day refreshes cost almost nothing.
- **Teams in no accessible table** (cross-border cup ties, uncovered leagues)
  fall back to a league-strength prior rather than a flat 1500, so a Premier
  League side is still favoured against a League Two one. Those cards are
  marked **est.**
- Season selection walks backwards until the plan returns data, so the same
  code uses current-season standings the moment you upgrade the key.

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
