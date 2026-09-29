/**
 * Reading a failed request.
 *
 * The four copies this replaces were identical, so the consolidation is not
 * where the risk is. The risk is `errorKind`, which is new behaviour: it
 * decides whether the user is shown a retry, and getting it wrong in the
 * generous direction — classifying something as retryable that is not — puts a
 * button on screen that cannot ever work.
 *
 * So the statuses are checked as a table, and the table asserts the three kinds
 * are actually distinguished rather than that each status returns *something*.
 */

import { describe, expect, it } from 'vitest';

import { errMessage, errorKind, httpStatus } from './errors';

/** An axios-shaped rejection, which is the only kind these functions ever see. */
function apiError(status: number, detail?: string): unknown {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data: detail === undefined ? {} : { detail } },
  });
}

describe('errMessage', () => {
  it("prefers the server's own explanation", () => {
    // The reason the `detail` lookup exists at all: axios's own message is
    // "Request failed with status code 422", which tells the user nothing they
    // can act on. Both strings are asserted so the test cannot pass by
    // accidentally returning either.
    const message = errMessage(apiError(422, 'Column "id" is not nullable.'));
    expect(message).toBe('Column "id" is not nullable.');
    expect(message).not.toContain('422');
  });

  it("falls back to the exception's message when there is no detail", () => {
    expect(errMessage(new Error('Network Error'))).toBe('Network Error');
  });

  it('falls back to the caller\'s wording when there is no message', () => {
    // `ExportPanel` says "Export failed." here, which is the only difference
    // between the four copies this replaced — so it has to survive.
    expect(errMessage({}, 'Export failed.')).toBe('Export failed.');
    expect(errMessage(new Error(''), 'Export failed.')).toBe('Export failed.');
  });

  it('has a fallback of its own', () => {
    expect(errMessage(undefined)).toBe('Request failed.');
  });
});

describe('httpStatus', () => {
  it('reads the status off a rejected request', () => {
    expect(httpStatus(apiError(403))).toBe(403);
  });

  it('is undefined when the request never got a response', () => {
    // A connection refused or a timeout. Treating a missing status as 0 or 500
    // would misclassify the appliance being down as a permission problem.
    expect(httpStatus(new Error('Network Error'))).toBeUndefined();
    expect(httpStatus(null)).toBeUndefined();
  });
});

describe('errorKind', () => {
  const CASES: [number | undefined, string][] = [
    [403, 'denied'],
    [404, 'missing'],
    [400, 'error'],
    [401, 'error'],
    [422, 'error'],
    [500, 'error'],
    [undefined, 'error'],
  ];

  it('has more than one outcome in its table', () => {
    // Precondition: a table that mapped everything to 'error' would satisfy
    // every row below individually and prove nothing about the distinction.
    expect(new Set(CASES.map(([, kind]) => kind)).size).toBeGreaterThan(1);
  });

  it.each(CASES)('classifies %s as %s', (status, kind) => {
    const error = status === undefined ? new Error('offline') : apiError(status);
    expect(errorKind(error)).toBe(kind);
  });

  it('leaves 401 to the interceptor', () => {
    // Not an oversight. `lib/api.ts` already clears the session and opens the
    // sign-in modal on 401, so by the time a component sees it the remedy is on
    // screen — calling it "denied" would put a second, contradictory message
    // underneath the one that is actually actionable.
    expect(errorKind(apiError(401))).toBe('error');
  });

  it('never calls a failure with no response denied', () => {
    // The appliance being unreachable is the most common failure in an
    // air-gapped deployment, and it is the one that must stay retryable.
    expect(errorKind(new Error('Network Error'))).toBe('error');
  });
});
