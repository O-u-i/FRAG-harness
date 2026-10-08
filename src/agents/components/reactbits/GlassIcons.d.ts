import type { ReactNode } from 'react';
export default function GlassIcons(props: { items: { icon: ReactNode; label: string; color: string; customClass?: string;
  onClick?: () => void; expanded?: boolean; controls?: string }[]; className?: string }): ReactNode;
