/**
 * Shown while /settings/classification's code is being fetched on navigation.
 *
 * Not the same thing as its data loading: the page fetches from the client,
 * so this covers the gap before the segment renders at all.
 */

import { LoadingState } from '@/components/ui';

export default function SettingsClassificationLoading() {
  return <LoadingState label="Loading the classification scale…" />;
}
