"use client";

interface EmptySectionProps {
  label: string;
}

export function EmptySection({ label }: EmptySectionProps) {
  return (
    <div className="text-center py-8">
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
