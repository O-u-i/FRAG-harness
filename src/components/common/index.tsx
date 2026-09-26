export function PanelHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="section-heading"><h2>{title}</h2><p>{subtitle}</p></div>;
}
