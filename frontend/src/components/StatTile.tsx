interface Props {
  label: string;
  value: string;
  sublabel?: string;
}

export function StatTile({ label, value, sublabel }: Props) {
  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <div className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
      {sublabel && (
        <div className="mt-0.5 text-xs" style={{ color: "var(--text-secondary)" }}>
          {sublabel}
        </div>
      )}
    </div>
  );
}
