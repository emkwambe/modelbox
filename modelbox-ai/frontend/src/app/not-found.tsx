/**
 * The 404. There was none, so an unknown path rendered Next.js's stock page —
 * unstyled, unbranded, and with no way back into the app.
 */

import Link from 'next/link';

import { ErrorState } from '@/components/ui';

export default function NotFound() {
  return (
    <ErrorState kind="missing" title="That page does not exist">
      {/*
        A route the user reached by typing or by following a stale link. The
        only useful thing to offer is the way back, and it is a real `<Link>`
        rather than a retry: re-rendering a path that does not exist produces
        the same 404 again.
      */}
      <Link href="/">Go to the home page</Link>
    </ErrorState>
  );
}
