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

// Matches the per-card ConfidenceBadge colours so the bands read as the
// same thing in both places.
const BAND = [
  { key: "high", label: "High", tone: "text-good" },
  { key: "medium", label: "Medium", tone: "text-warn" },
  { key: "low", label: "Low", tone: "text-serious" },
];

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: number | null | undefined;
  sub?: string;
  tone?: string;
}) {
  if (value == null) return null;
  return (
    <div className="flex flex-col items-center px-4">
      <span className={`text-lg font-bold tabular-nums ${tone ?? ""}`}>
        {(value * 100).toFixed(0)}%
      </span>
      <span className="text-[11px] uppercase tracking-wide text-muted">
        {label}
        {sub && <span className="ml-1 normal-case tabular-nums">({sub})</span>}
      </span>
    </div>
  );
}

export default function AccuracyBar({ accuracy }: { accuracy: AccuracySummary }) {
  const bands = accuracy.confidence_accuracy ?? {};
  const hasBands = Object.keys(bands).length > 0;
  const bandTotal = Object.values(bands).reduce((n, b) => n + b.graded, 0);

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

      {hasBands && (
        <div className="mt-1 flex w-full flex-wrap items-center border-t border-line pt-3">
          <span
            className="pr-4 text-xs font-semibold text-ink2"
            title="How often the model's pick was right, split by the confidence it claimed. High should outperform low — if it doesn't, the confidence is miscalibrated."
          >
            By confidence
          </span>
          <div className="flex flex-wrap divide-x divide-line">
            {BAND.map(({ key, label, tone }) =>
              bands[key] ? (
                <Stat
                  key={key}
                  label={label}
                  value={bands[key].accuracy}
                  sub={String(bands[key].graded)}
                  tone={tone}
                />
              ) : null
            )}
            <Stat
              label="Overall"
              value={accuracy.pick_accuracy}
              sub={String(bandTotal)}
            />
          </div>
        </div>
      )}

      {accuracy.ai_overall != null && (
        <div className="mt-1 flex w-full flex-wrap items-center border-t border-line pt-3">
          <span className="pr-4 text-xs font-semibold text-ink2">✦ Claude</span>
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
