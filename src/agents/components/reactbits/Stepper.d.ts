import type { ReactNode } from 'react';
export default function Stepper(props: { children: ReactNode; step?: number; reachedStep?: number; labels?: string[];
  headerOnly?: boolean; onStepChange?: (step: number) => void; className?: string }): ReactNode;
