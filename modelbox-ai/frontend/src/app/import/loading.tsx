/**
 * Shown while /import's code is being fetched on navigation. The page's own
 * fetch states are the page's.
 */

import { LoadingState } from '@/components/ui';

export default function ImportLoading() {
  return <LoadingState label="Loading the import page…" />;
}
