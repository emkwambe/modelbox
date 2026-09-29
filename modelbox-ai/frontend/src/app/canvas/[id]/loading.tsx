/**
 * Shown while /canvas/<id>'s code is being fetched on navigation. Reading the
 * model itself is the page's own loading state.
 */

import { LoadingState } from '@/components/ui';

export default function CanvasModelLoading() {
  return <LoadingState label="Loading the canvas…" />;
}
