import type { ReactNode } from 'react';
export type MenuItem = { value?: string; label: string; icon?: ReactNode; children?: { value: string; label: string; icon?: ReactNode }[] };
export default function BranchedMenu(props: { items: MenuItem[]; activeValue?: string; defaultOpen?: number | number[]; defaultActive?: string;
  onSelect?: (value: string) => void; onToggle?: (index: number, open: boolean) => void; width?: number; rowHeight?: number;
  indent?: number; trunk?: number; fontSize?: number; className?: string }): ReactNode;
