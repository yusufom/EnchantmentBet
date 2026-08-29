import type { AccuracySummary } from "@/lib/types";

const MARKET_LABEL: Record<string, string> = {
  "over_under_2.5": "O/U 2.5",
  "over_under_1.5": "O/U 1.5",
  btts: "BTTS",
  winner: "Winner",
  double_chance: "Dbl chance",
  first_half_winner: "1st half",
  total_points: "Total",
};

function Stat({ label, value }: { label: string; value: number | null | undefined }) {
  if (value == null) return null;
  return (
    <div className="flex flex-col items-center px-4">
      <span className="text-lg font-bold tabular-nums">{(value * 100).toFixed(0)}%</span>
      <span className="text-[11px] uppercase tracking-wide text-muted">{label}</span>
    </div>
  );
}

export default function AccuracyBar({ accuracy }: { accuracy: AccuracySummary }) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-y-3 rounded-2xl border border-line bg-surface px-4 py-3">
      <div className="flex flex-col pr-4">
        <span className="text-sm font-semibold">Day accuracy</span>
        <span className="text-xs text-muted">
          {accuracy.graded} of {accuracy.total} fixtures settled
        </span>
      </div>
      <div className="flex flex-wrap divide-x divide-line">
        <Stat label="Picks" value={accuracy.pick_accuracy} />
        {Object.entries(accuracy.market_accuracy).map(([market, value]) => (
          <Stat key={market} label={MARKET_LABEL[market] ?? market} value={value} />
        ))}
        <Stat label="Exact score" value={accuracy.exact_score_accuracy} />
      </div>
      {accuracy.ai_overall != null && (
        <div className="flex w-full flex-wrap items-center border-t border-line pt-3 mt-1">
          <span className="pr-4 text-xs font-semibold text-ink2">
            ✦ Claude
          </span>
          <div className="flex flex-wrap divide-x divide-line">
            <Stat label="All picks" value={accuracy.ai_overall} />
            {Object.entries(accuracy.ai_accuracy).map(([market, value]) => (
              <Stat key={market} label={MARKET_LABEL[market] ?? market} value={value} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
