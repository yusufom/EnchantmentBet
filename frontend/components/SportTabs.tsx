"use client";

import type { SportFilter } from "@/lib/types";

const TABS: { value: SportFilter; label: string; icon: string }[] = [
  { value: "all", label: "All", icon: "◎" },
  { value: "football", label: "Football", icon: "⚽" },
  { value: "basketball", label: "Basketball", icon: "🏀" },
  { value: "tennis", label: "Tennis", icon: "🎾" },
];

export default function SportTabs({
  sport,
  onChange,
}: {
  sport: SportFilter;
  onChange: (sport: SportFilter) => void;
}) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1">
      {TABS.map((tab) => {
        const active = tab.value === sport;
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={`rounded-lg px-3.5 py-1.5 text-sm transition-colors ${
              active
                ? "bg-raised text-ink font-semibold"
                : "text-ink2 hover:text-ink"
            }`}
          >
            <span aria-hidden className="mr-1.5">{tab.icon}</span>
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
