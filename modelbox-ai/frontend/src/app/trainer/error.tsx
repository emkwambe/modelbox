'use client';

/**
 * The error boundary for /trainer. Wording only — the behaviour is
 * `RouteError`, which is where the reasoning and the tests live.
 */

import RouteError from '@/components/ui/RouteError';
import type { RouteErrorProps } from '@/components/ui/RouteError';

export default function TrainerError(
  props: Omit<RouteErrorProps, 'surface'>,
) {
  return <RouteError {...props} surface="The trainer" />;
}
