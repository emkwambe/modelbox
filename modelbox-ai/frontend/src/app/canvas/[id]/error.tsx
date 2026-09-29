'use client';

/**
 * The error boundary for /canvas/<id>. Wording only — the behaviour is
 * `RouteError`, which is where the reasoning and the tests live.
 */

import RouteError from '@/components/ui/RouteError';
import type { RouteErrorProps } from '@/components/ui/RouteError';

export default function CanvasModelError(
  props: Omit<RouteErrorProps, 'surface'>,
) {
  return <RouteError {...props} surface="This model's canvas" />;
}
