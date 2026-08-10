"use client";

function shiftDate(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function todayISO(): string {
  return new Date().toLocaleDateString("en-CA");
}

export default function DateNav({
  date,
  onChange,
}: {
  date: string;
  onChange: (date: string) => void;
}) {
  const navBtn =
    "rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink2 hover:bg-raised hover:text-ink transition-colors";
  return (
    <div className="flex items-center gap-2">
      <button
        className={navBtn}
        aria-label="Previous day"
        onClick={() => onChange(shiftDate(date, -1))}
      >
        ‹
      </button>
      <input
        type="date"
        value={date}
        suppressHydrationWarning
        onChange={(e) => e.target.value && onChange(e.target.value)}
        className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink [color-scheme:dark]"
      />
      <button
        className={navBtn}
        aria-label="Next day"
        onClick={() => onChange(shiftDate(date, 1))}
      >
        ›
      </button>
      <button className={navBtn} onClick={() => onChange(todayISO())}>
        Today
      </button>
    </div>
  );
}
