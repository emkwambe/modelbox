/**
 * Shown while /settings/api-keys's code is being fetched on navigation.
 *
 * Not the same thing as its data loading: every page here fetches from the
 * client, so this covers the gap before the segment renders at all. The
 * in-page fetch states are the page's own.
 */

import { LoadingState } from '@/components/ui';

export default function SettingsApiKeysLoading() {
  return <LoadingState label="Loading API keys…" />;
}
