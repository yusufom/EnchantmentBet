"use client";

/**
 * Proportional outcome bar: home / (draw) / away.
 * Diverging structure — blue and orange poles with a neutral gray draw
 * segment. Every segment is always direct-labeled in the legend row below,
 * so color never carries the value alone.
 */
export default function OutcomeBar({
  homeLabel,
  awayLabel,
  home,
  away,
  draw,
}: {
  homeLabel: string;
  awayLabel: string;
  home: number;
  away: number;
  draw?: number;
}) {
  const segments = [
    { key: "home", label: homeLabel, value: home, color: "bg-home" },
    ...(draw !== undefined
      ? [{ key: "draw", label: "Draw", value: draw, color: "bg-draw" }]
      : []),
    { key: "away", label: awayLabel, value: away, color: "bg-away" },
  ];
  const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

  return (
    <div>
      <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded">
        {segments.map((s) => (
          <div
            key={s.key}
            className={`${s.color} first:rounded-l last:rounded-r`}
            style={{ width: `${Math.max(s.value * 100, 1.5)}%` }}
            title={`${s.label} ${pct(s.value)}`}
          />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {segments.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-ink2">
            <span aria-hidden className={`h-2 w-2 rounded-sm ${s.color}`} />
            <span className="max-w-[9rem] truncate">{s.label}</span>
            <span className="font-semibold text-ink">{pct(s.value)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
