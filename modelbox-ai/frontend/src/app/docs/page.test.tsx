/**
 * F2 on `/docs` — two defects, both of which looked like nothing on screen.
 *
 * 1. **`catch {}` around the fetch.** "Still loading" was inferred from
 *    `text[tab] === ''`, which is also what a failed fetch leaves behind, so a
 *    backend that never served the guide showed "Loading documentation…" for as
 *    long as the page stayed open. Not a slow page — a permanently wrong one.
 * 2. **`res.ok` was never checked.** `fetch` rejects on a transport failure and
 *    resolves on a 404, so the error page's HTML body was handed to the
 *    Markdown renderer and displayed *as documentation*.
 *
 * The second is the one no amount of care at the call site would have caught,
 * because the code reads correctly: it awaits, it handles the throw, and the
 * throw never comes.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DocsPage from './page';

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A `fetch` result, which is the only shape this page reads. */
function response(body: string, { ok = true, status = 200 } = {}) {
  return Promise.resolve({ ok, status, text: () => Promise.resolve(body) });
}

describe('DocsPage', () => {
  it('renders the guide once it arrives', async () => {
    fetchMock.mockImplementation(() => response('# Getting started'));
    render(<DocsPage />);

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Getting started' }),
      ).toBeInTheDocument(),
    );
  });

  it('says it is loading before anything arrives', () => {
    // Never resolves. The point is the state *while* the request is open —
    // which is the only state the old code could express correctly.
    fetchMock.mockImplementation(() => new Promise(() => {}));
    render(<DocsPage />);

    expect(screen.getByRole('status')).toHaveTextContent('Loading documentation…');
  });

  it('stops claiming to load when the fetch fails', async () => {
    fetchMock.mockRejectedValue(new Error('Failed to fetch'));
    render(<DocsPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('User Guide could not be loaded');
    expect(alert).toHaveTextContent('Failed to fetch');
    // The half that names the defect: the old page showed this forever.
    expect(screen.queryByText('Loading documentation…')).toBeNull();
  });

  it('does not render a 404 page as documentation', async () => {
    // `fetch` resolves on a 404, so without an `res.ok` check this body is
    // rendered as Markdown and the user reads Next.js's error page as if it
    // were the user guide.
    fetchMock.mockImplementation(() =>
      response('<h1>404: This page could not be found.</h1>', {
        ok: false,
        status: 404,
      }),
    );
    render(<DocsPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('404');
    expect(screen.queryByText(/could not be found/)).toBeNull();
  });

  it('retries the fetch when asked', async () => {
    fetchMock.mockRejectedValue(new Error('Failed to fetch'));
    render(<DocsPage />);
    await screen.findByRole('alert');

    const before = fetchMock.mock.calls.length;
    expect(before).toBeGreaterThan(0);

    fetchMock.mockImplementation(() => response('# Getting started'));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Getting started' }),
      ).toBeInTheDocument(),
    );
    // A retry that re-rendered without re-requesting would satisfy the
    // assertion above on a cached success and prove nothing.
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before);
  });
});
