"use client";

import { useEffect, useState } from "react";

import type { Market, MarketGrade, Prediction } from "@/lib/types";

import ConfidenceBadge from "./ConfidenceBadge";
import OutcomeBar from "./OutcomeBar";

const FACT_ICON: Record<string, string> = {
  market: "◎",
  venue: "⌂",
  weather: "☁",
  referee: "⚑",
  absence: "✚",
  h2h: "⇄",
  form: "▲",
};

const AI_MARKET_LABEL: Record<string, string> = {
  winner: "Winner",
  double_chance: "Double chance",
  "over_under_1.5": "O/U 1.5",
  "over_under_2.5": "O/U 2.5",
  btts: "BTTS",
  first_half_winner: "1st half",
  total_points: "Total",
};

const AI_MARKET_ORDER = Object.keys(AI_MARKET_LABEL);

function aiPickLabel(
  market: string,
  pick: string,
  homeName: string,
  awayName: string
): string {
  const short = (n: string) => (n.length > 12 ? `${n.slice(0, 11)}…` : n);
  if (market === "winner" || market === "first_half_winner") {
    return pick === "1" ? short(homeName) : pick === "2" ? short(awayName) : "Draw";
  }
  if (market === "double_chance") return pick;
  return pick.charAt(0).toUpperCase() + pick.slice(1);
}

const SPORT_ICON: Record<string, string> = {
  football: "⚽",
  basketball: "🏀",
  tennis: "🎾",
};

function TimeLabel({ iso }: { iso?: string | null }) {
  const [label, setLabel] = useState("");
  useEffect(() => {
    if (!iso) return;
    setLabel(
      new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    );
  }, [iso]);
  return <span suppressHydrationWarning>{label}</span>;
}

function marketChip(market: Market): string | null {
  const pct = (v: number) => `${(v * 100).toFixed(0)}%`;
  if (market.name.startsWith("over_under_")) {
    const line = market.name.replace("over_under_", "");
    return `O/U ${line}: ${market.pick === "over" ? "Over" : "Under"} ${pct(market.pick_probability)}`;
  }
  if (market.name === "btts") {
    return `BTTS: ${market.pick === "yes" ? "Yes" : "No"} ${pct(market.pick_probability)}`;
  }
  if (market.name.startsWith("total_")) {
    return `Proj. total ${market.name.replace("total_", "")}`;
  }
  if (market.name === "set_score") {
    return `Sets ${market.pick} ${pct(market.pick_probability)}`;
  }
  return null;
}

const IMPACT_DOT: Record<string, string> = {
  positive_home: "bg-home",
  positive_away: "bg-away",
  neutral: "bg-draw",
};

export default function PredictionCard({ prediction }: { prediction: Prediction }) {
  const { fixture } = prediction;
  const main = prediction.markets[0];
  const secondary = prediction.markets.slice(1);
  const isTennis = fixture.sport === "tennis";

  const pickName =
    main.pick === "home"
      ? fixture.home.name
      : main.pick === "away"
        ? fixture.away.name
        : "Draw";

  return (
    <article className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5">
      <header className="flex items-center justify-between gap-2 text-xs text-muted">
        <span className="truncate">
          <span aria-hidden className="mr-1.5">{SPORT_ICON[fixture.sport]}</span>
          {fixture.league}
          {fixture.surface ? ` · ${fixture.surface}` : ""}
          {fixture.round ? ` · ${fixture.round}` : ""}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {(prediction.data_quality ?? 1) < 0.7 && (
            <span
              className="rounded-full border border-line px-1.5 py-0.5 text-[10px] text-warn"
              title="No season stats for one or both teams — this prediction leans on a league-strength estimate."
            >
              est.
            </span>
          )}
          <TimeLabel iso={fixture.start_time} />
        </span>
      </header>

      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <CompetitorRow name={fixture.home.name} logo={fixture.home.logo} />
          <div className="my-1 text-[11px] uppercase tracking-wide text-muted">
            {isTennis ? "vs" : "v"}
          </div>
          <CompetitorRow name={fixture.away.name} logo={fixture.away.logo} />
        </div>
        {prediction.result ? (
          <div className="shrink-0 text-right">
            <div className="text-[11px] uppercase tracking-wide text-muted">
              Final ({prediction.result.status})
            </div>
            <div className="text-2xl font-bold tabular-nums">
              {prediction.result.home_score}-{prediction.result.away_score}
            </div>
            <div className="text-[11px] text-muted tabular-nums">
              predicted {prediction.predicted_score}
            </div>
          </div>
        ) : prediction.predicted_score ? (
          <div className="shrink-0 text-right">
            <div className="text-[11px] uppercase tracking-wide text-muted">
              {isTennis ? "Sets" : "Score"}
            </div>
            <div className="text-2xl font-bold tabular-nums">
              {prediction.predicted_score}
            </div>
            {prediction.expected_home != null && prediction.expected_away != null && (
              <div className="text-[11px] text-muted tabular-nums">
                exp {prediction.expected_home.toFixed(1)}–{prediction.expected_away.toFixed(1)}
              </div>
            )}
          </div>
        ) : null}
      </div>

      <OutcomeBar
        homeLabel={fixture.home.name}
        awayLabel={fixture.away.name}
        home={main.outcomes.home ?? 0}
        away={main.outcomes.away ?? 0}
        draw={"draw" in main.outcomes ? main.outcomes.draw : undefined}
      />

      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 text-sm">
          <span className="text-muted">Pick: </span>
          <span className="font-semibold">{pickName}</span>
          <span className="ml-1.5 text-ink2 tabular-nums">
            {(main.pick_probability * 100).toFixed(0)}%
          </span>
        </div>
        {prediction.pick_correct != null ? (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-raised px-2.5 py-1 text-xs font-medium ${
              prediction.pick_correct ? "text-good" : "text-serious"
            }`}
          >
            <span aria-hidden>{prediction.pick_correct ? "✓" : "✗"}</span>
            {prediction.pick_correct ? "Pick hit" : "Pick missed"}
          </span>
        ) : (
          <ConfidenceBadge label={prediction.confidence_label} value={prediction.confidence} />
        )}
      </div>

      {(prediction.match_facts?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-line bg-raised/40 p-3">
          <div className="mb-2 text-xs font-semibold text-ink">Match facts</div>
          <ul className="flex flex-col gap-1.5">
            {prediction.match_facts!.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span aria-hidden className="mt-px w-3 shrink-0 text-center text-muted">
                  {FACT_ICON[f.category] ?? "•"}
                </span>
                <span className="min-w-0">
                  <span className="text-muted">{f.label}: </span>
                  <span className="text-ink2">{f.value}</span>
                </span>
              </li>
            ))}
          </ul>
          {prediction.odds?.match_winner && (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-line pt-2 text-[11px] text-muted">
              <span className="font-semibold text-ink2">Market</span>
              {(["home", "draw", "away"] as const).map((k) =>
                prediction.odds!.match_winner[k] != null ? (
                  <span key={k} className="tabular-nums">
                    {k === "home"
                      ? fixture.home.name
                      : k === "away"
                        ? fixture.away.name
                        : "Draw"}{" "}
                    <span className="font-semibold text-ink2">
                      {(prediction.odds!.match_winner[k] * 100).toFixed(0)}%
                    </span>
                  </span>
                ) : null
              )}
            </div>
          )}
        </div>
      )}

      {prediction.ai && (
        <div className="rounded-xl border border-home/30 bg-raised/60 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-ink">
              ✦ Claude&apos;s prediction
            </span>
            <span className="text-[11px] text-muted tabular-nums">
              confidence {(prediction.ai.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {AI_MARKET_ORDER.filter((m) => prediction.ai!.picks[m]).map((market) => {
              const pick = prediction.ai!.picks[market];
              const grade: MarketGrade | undefined = prediction.ai_grades?.find(
                (g) => g.market === market
              );
              return (
                <span
                  key={market}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
                    grade
                      ? grade.correct
                        ? "border-good/40 text-good"
                        : "border-serious/40 text-serious"
                      : "border-line text-ink2"
                  }`}
                  title={grade ? `actual: ${grade.actual}` : undefined}
                >
                  {grade && <span aria-hidden>{grade.correct ? "✓" : "✗"}</span>}
                  <span className="text-muted">{AI_MARKET_LABEL[market]}:</span>
                  <span className="font-semibold">
                    {aiPickLabel(market, pick, fixture.home.name, fixture.away.name)}
                  </span>
                </span>
              );
            })}
          </div>
          {prediction.ai.analysis && (
            <p className="mt-2 text-xs leading-relaxed text-ink2">
              {prediction.ai.analysis}
            </p>
          )}
        </div>
      )}
      {!prediction.ai && prediction.insight && (
        <p className="border-l-2 border-home/60 pl-3 text-xs leading-relaxed text-ink2">
          <span className="mr-1 font-semibold text-ink">Claude&apos;s read:</span>
          {prediction.insight}
        </p>
      )}

      {secondary.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {secondary.map((m) => {
            const chip = marketChip(m);
            return chip ? (
              <span
                key={m.name}
                className="rounded-full border border-line bg-raised px-2.5 py-1 text-xs text-ink2"
              >
                {chip}
              </span>
            ) : null;
          })}
        </div>
      )}

      {prediction.factors.length > 0 && (
        <ul className="flex flex-col gap-1.5 border-t border-line pt-3">
          {prediction.factors.slice(0, 4).map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-xs">
              <span
                aria-hidden
                className={`mt-1 h-2 w-2 shrink-0 rounded-full ${IMPACT_DOT[f.impact]}`}
              />
              <span className="min-w-0">
                <span className="text-ink2">{f.label}</span>
                {f.detail && <span className="text-muted"> — {f.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {prediction.news.length > 0 && (
        <details className="border-t border-line pt-3 text-xs">
          <summary className="cursor-pointer text-muted hover:text-ink2">
            Team news ({prediction.news.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {prediction.news.map((n, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  aria-hidden
                  className={
                    n.sentiment > 0.05
                      ? "text-good"
                      : n.sentiment < -0.05
                        ? "text-serious"
                        : "text-muted"
                  }
                >
                  {n.sentiment > 0.05 ? "▲" : n.sentiment < -0.05 ? "▼" : "•"}
                </span>
                <span className="min-w-0 text-ink2">
                  {n.headline}
                  {n.source && <span className="text-muted"> — {n.source}</span>}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

function CompetitorRow({ name, logo }: { name: string; logo?: string | null }) {
  return (
    <div className="flex items-center gap-2">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt="" className="h-5 w-5 object-contain" />
      ) : null}
      <span className="truncate font-semibold">{name}</span>
    </div>
  );
}
