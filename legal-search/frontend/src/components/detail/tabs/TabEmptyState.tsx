"use client";

interface TabEmptyStateProps {
  title: string;
  description: string;
}

export function TabEmptyState({ title, description }: TabEmptyStateProps) {
  return (
    <div className="px-5 py-6">
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-4 py-5 text-center">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="mx-auto mt-1.5 max-w-[24rem] text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      </div>
    </div>
  );
}
