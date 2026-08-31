/**
 * Reading a failed request.
 *
 * `errMessage` existed four times — in `api-keys`, `connectors`, `ExportPanel`
 * and `DiffPanel` — byte-identical apart from the fallback string. That is the
 * uninteresting half of why this file exists.
 *
 * The interesting half is that all four threw away the status code, and the
 * status is the only thing that distinguishes failures the user can do
 * something about from failures they cannot. `lib/api.ts` clears the session on
 * 401 and lets everything else fall through to one generic path, so a 403 is
 * reported as "something went wrong" and offered a retry that is guaranteed to
 * fail. `errorKind` is that distinction, and it is here rather than in a
 * component so the API layer owns it.
 */

/** How a failure should be presented. Decided by the status, not by the caller. */
export type ErrorKind = 'error' | 'denied' | 'missing';

/** The HTTP status of a rejected request, if it got far enough to have one. */
export function httpStatus(e: unknown): number | undefined {
  if (typeof e !== 'object' || e === null || !('response' in e)) return undefined;
  const response = (e as { response?: { status?: unknown } }).response;
  const status = response?.status;
  return typeof status === 'number' ? status : undefined;
}

/**
 * The server's own explanation, falling back to the exception's message and
 * then to `fallback`.
 *
 * FastAPI puts it in `detail`, and preferring it matters: the message axios
 * produces is "Request failed with status code 422", which tells the user
 * nothing they can act on.
 */
export function errMessage(e: unknown, fallback = 'Request failed.'): string {
  if (
    typeof e === 'object' &&
    e !== null &&
    'response' in e &&
    typeof (e as { response?: unknown }).response === 'object'
  ) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response
      ?.data?.detail;
    if (typeof detail === 'string') return detail;
  }
  return e instanceof Error && e.message ? e.message : fallback;
}

/**
 * Which of the three failures this is.
 *
 * 403 is not an error and must not be retried — the answer will be the same the
 * second time, and offering a button that cannot work is worse than offering
 * none. 404 is not an error either: nothing broke, the thing is not there.
 *
 * 401 is deliberately *not* mapped here. The response interceptor in
 * `lib/api.ts` already clears the session and opens the sign-in modal, so by
 * the time a component sees it the remedy is on screen; classifying it as
 * "denied" would put a second, contradictory message underneath.
 */
export function errorKind(e: unknown): ErrorKind {
  const status = httpStatus(e);
  if (status === 403) return 'denied';
  if (status === 404) return 'missing';
  return 'error';
}
