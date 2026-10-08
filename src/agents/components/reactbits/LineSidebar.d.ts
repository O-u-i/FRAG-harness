import type { ReactNode } from 'react';
export default function LineSidebar(props: { items: string[]; active?: number | null; defaultActive?: number | null;
  onItemClick?: (index: number) => void; accentColor?: string; textColor?: string; showIndex?: boolean; markerLength?: number;
  maxShift?: number; itemGap?: number; fontSize?: number; className?: string }): ReactNode;
