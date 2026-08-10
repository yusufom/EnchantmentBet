const STYLE: Record<string, { dot: string; text: string; label: string }> = {
  high: { dot: "bg-good", text: "text-good", label: "High confidence" },
  medium: { dot: "bg-warn", text: "text-warn", label: "Medium confidence" },
  low: { dot: "bg-serious", text: "text-serious", label: "Low confidence" },
};

export default function ConfidenceBadge({
  label,
  value,
}: {
  label: "low" | "medium" | "high";
  value: number;
}) {
  const s = STYLE[label];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-raised px-2.5 py-1 text-xs font-medium ${s.text}`}
      title={`Model confidence ${(value * 100).toFixed(0)}%`}
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
