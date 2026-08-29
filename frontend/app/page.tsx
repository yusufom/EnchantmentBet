"use client";

import { useEffect, useState } from "react";

import AccuracyBar from "@/components/AccuracyBar";
import DateNav, { todayISO } from "@/components/DateNav";
import PredictionCard from "@/components/PredictionCard";
import SkeletonCard from "@/components/SkeletonCard";
import SportTabs from "@/components/SportTabs";
import {
  usePredictions,
  useRefreshPredictions,
  useRefreshResults,
} from "@/hooks/usePredictions";
import type { Sport } from "@/lib/types";

function LastRefreshed({ iso }: { iso?: string }) {
  const [label, setLabel] = useState("");
  useEffect(() => {
    if (!iso) return;
    setLabel(new Date(iso).toLocaleString());
  }, [iso]);
  if (!iso) return null;
  return <span suppressHydrationWarning>Last refreshed {label}</span>;
}

export default function Home() {
  const [date, setDate] = useState(todayISO);
  const [sport, setSport] = useState<Sport>("football");

  const { data, isLoading, isError, error, refetch } = usePredictions(date, sport);
  const refresh = useRefreshPredictions();
  const results = useRefreshResults();

  const predictions = data?.predictions ?? [];
  const meta = data?.meta ?? [];
  const latestRefresh = meta
    .map((m) => m.refreshed_at)
    .sort()
    .at(-1);
  const isMock = meta.some((m) => m.data_source === "mock");

  const doRefresh = () => refresh.mutate({ date, sport });

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            ✨ EnchantmentBet
          </h1>
          <p className="mt-1 text-sm text-ink2">
            Statistical football &amp; basketball predictions — form, injuries
            and team news factored in. Each sport refreshes and settles
            independently.
          </p>
        </div>
        <div className="text-right text-xs text-muted">
          <LastRefreshed iso={latestRefresh} />
          {isMock && (
            <div className="mt-1 inline-block rounded-full border border-line bg-raised px-2 py-0.5">
              sample data — add API keys for live fixtures
            </div>
          )}
        </div>
      </header>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <DateNav date={date} onChange={setDate} />
          <SportTabs sport={sport} onChange={setSport} />
        </div>
        <div className="flex items-center gap-2">
          {predictions.length > 0 && (
            <button
              onClick={() => results.mutate({ date, sport })}
              disabled={results.isPending}
              className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink2 transition-colors hover:bg-raised hover:text-ink disabled:opacity-50"
            >
              {results.isPending && (
                <span
                  aria-hidden
                  className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink2/40 border-t-ink2"
                />
              )}
              {results.isPending ? "Fetching scores…" : "Update results"}
            </button>
          )}
          <button
            onClick={doRefresh}
            disabled={refresh.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-home px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {refresh.isPending && (
              <span
                aria-hidden
                className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
              />
            )}
            {refresh.isPending ? "Refreshing…" : "Refresh predictions"}
          </button>
        </div>
      </div>

      {data?.accuracy && <AccuracyBar accuracy={data.accuracy} />}

      {(data?.errors?.length ?? 0) > 0 && (
        <div className="mb-4 rounded-lg border border-warn/40 bg-surface px-4 py-3 text-xs text-warn">
          <span aria-hidden className="mr-1.5">⚠</span>
          {data!.errors!.map((e, i) => (
            <div key={i} className="inline">{e} </div>
          ))}
        </div>
      )}

      {refresh.isError && (
        <p className="mb-4 rounded-lg border border-serious/40 bg-surface px-4 py-3 text-sm text-serious">
          Refresh failed: {(refresh.error as Error).message}
        </p>
      )}
      {results.isError && (
        <p className="mb-4 rounded-lg border border-serious/40 bg-surface px-4 py-3 text-sm text-serious">
          Fetching results failed: {(results.error as Error).message}
        </p>
      )}

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : isError ? (
        <div className="rounded-2xl border border-line bg-surface p-10 text-center">
          <p className="text-sm text-serious">
            Could not reach the prediction API — is the backend running on port
            8000?
          </p>
          <p className="mt-2 text-xs text-muted">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="mt-4 rounded-lg border border-line bg-raised px-4 py-2 text-sm text-ink hover:bg-line"
          >
            Retry
          </button>
        </div>
      ) : predictions.length === 0 ? (
        <div className="rounded-2xl border border-line bg-surface p-10 text-center">
          <p className="text-lg font-semibold">No predictions for {date} yet</p>
          <p className="mt-1 text-sm text-ink2">
            Pull the latest fixtures, form, injuries and news, then run the
            model for this date.
          </p>
          <button
            onClick={doRefresh}
            disabled={refresh.isPending}
            className="mt-5 rounded-lg bg-home px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {refresh.isPending ? "Generating…" : "Generate predictions"}
          </button>
        </div>
      ) : (
        <div className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {predictions.map((p) => (
            <PredictionCard key={`${p.sport}-${p.fixture_id}`} prediction={p} />
          ))}
        </div>
      )}

      <footer className="mt-10 border-t border-line pt-4 text-center text-xs text-muted">
        Predictions are statistical estimates, not guarantees. If you bet,
        bet responsibly.
      </footer>
    </main>
  );
}
