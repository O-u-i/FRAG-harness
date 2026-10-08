import type { ReactNode } from 'react';
export type Option = string | { value: string; label: ReactNode; tag?: ReactNode };
export default function GlideSelect(props: { options: Option[]; value?: string; defaultValue?: string; onChange?: (value: string) => void;
  ariaLabel: string; disabled?: boolean; placeholder?: string; size?: 'sm' | 'md' | 'lg'; menuWidth?: number; className?: string }): ReactNode;
