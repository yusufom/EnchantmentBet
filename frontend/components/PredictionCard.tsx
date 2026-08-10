"use client";

import { useEffect, useState } from "react";

import type { Market, Prediction } from "@/lib/types";
import ConfidenceBadge from "./ConfidenceBadge";
import OutcomeBar from "./OutcomeBar";

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
        <span className="shrink-0">
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
        {prediction.predicted_score && (
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
        )}
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
        <ConfidenceBadge label={prediction.confidence_label} value={prediction.confidence} />
      </div>

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
