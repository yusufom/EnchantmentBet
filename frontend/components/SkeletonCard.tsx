export default function SkeletonCard() {
  return (
    <div className="flex animate-pulse flex-col gap-4 rounded-2xl border border-line bg-surface p-5">
      <div className="h-3 w-2/5 rounded bg-raised" />
      <div className="space-y-2">
        <div className="h-4 w-3/5 rounded bg-raised" />
        <div className="h-4 w-1/2 rounded bg-raised" />
      </div>
      <div className="h-2.5 w-full rounded bg-raised" />
      <div className="h-3 w-4/5 rounded bg-raised" />
      <div className="h-8 w-full rounded bg-raised" />
    </div>
  );
}
