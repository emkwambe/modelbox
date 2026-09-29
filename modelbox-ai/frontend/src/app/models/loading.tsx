/**
 * Shown while /models's code is being fetched on navigation. The list's own
 * fetch state is the page's.
 */

import { LoadingState } from '@/components/ui';

export default function ModelsLoading() {
  return <LoadingState label="Loading the model list…" />;
}
