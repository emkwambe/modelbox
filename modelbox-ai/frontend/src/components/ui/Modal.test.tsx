/**
 * F2 — the dialog properties, asserted once on the primitive.
 *
 * Every one of these fails against the code this replaces. That is the point
 * of the file: the three hand-rolled modals are a `position: fixed` div with a
 * click handler, and a div has no role, no name, no focus trap, no Escape and
 * no focus restore. Six defects, one per test below, none of which any existing
 * test could see because the frontend had no test runner until this sprint.
 *
 * The behaviour is Radix's, not ours — so what is actually under test is that
 * this component *wires it up*, which is the part a rewrite can break. A
 * `Dialog.Content` rendered outside a `Dialog.Portal`, a `Dialog.Title`
 * replaced by a styled `<div>` because it was "just a heading", or a
 * `Dialog.Close` swapped for a plain `onClick={onClose}` all still render a
 * dialog that looks right and fails here.
 *
 * Mutation, 2026-08-31: replacing `Dialog.Title` with a `<div>` carrying the
 * same class fails the accessible-name test and the heading test, and nothing
 * else — the dialog still renders, still closes, still traps focus. That is the
 * shape of the defect that shipped.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import Modal from './Modal';
import Button from './Button';

function open(props: Partial<ComponentProps<typeof Modal>> = {}) {
  const onClose = vi.fn();
  const utils = render(
    <Modal title="Spot the Flaw — Labs" onClose={onClose} {...props}>
      <Button>Start lab</Button>
    </Modal>,
  );
  return { onClose, ...utils };
}

describe('Modal', () => {
  it('is a dialog', () => {
    open();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('takes the page behind it out of the accessibility tree', () => {
    render(
      <>
        <button type="button">behind the overlay</button>
        <Modal title="Labs" onClose={() => {}}>
          <Button>Start lab</Button>
        </Modal>
      </>,
    );

    // The assertion is deliberately about the *consequence*, not about an
    // attribute: the button behind the overlay is no longer reachable by role,
    // because Radix marks everything outside the dialog `aria-hidden`. A
    // `position: fixed` div hides that content visually and leaves every bit of
    // it in the accessibility tree, so a screen-reader user browsing the page
    // walks straight through the dialog into content they cannot see.
    //
    // Checked this way rather than against `aria-modal`, which this version of
    // Radix does not emit — asserting the attribute would have been asserting
    // the documentation instead of the component.
    expect(screen.getByText('behind the overlay')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'behind the overlay' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Start lab' })).toBeInTheDocument();
  });

  it('is announced by its title', () => {
    open();
    // Queried by accessible name rather than by text: this passes only if the
    // title is wired to the dialog through `aria-labelledby`, which is exactly
    // what a bold `<div>` does not do.
    expect(
      screen.getByRole('dialog', { name: 'Spot the Flaw — Labs' }),
    ).toBeInTheDocument();
  });

  it('renders the title as a heading, not as a bold div', () => {
    open();
    expect(
      screen.getByRole('heading', { name: 'Spot the Flaw — Labs' }),
    ).toBeInTheDocument();
  });

  it('describes itself when given a description, and does not when not', () => {
    const { unmount } = open({ description: 'Load a flawed model and fix it.' });

    const described = screen.getByRole('dialog');
    const id = described.getAttribute('aria-describedby');
    expect(id).toBeTruthy();
    // Resolved through the document rather than compared as a string: an
    // attribute pointing at an id that does not exist announces nothing, and a
    // string comparison passes on it happily.
    expect(document.getElementById(id ?? '')?.textContent).toBe(
      'Load a flawed model and fix it.',
    );

    unmount();
    open();
    // The precondition for the assertion above. Without it, a component that
    // always emitted the attribute would satisfy the first half on a stale or
    // empty value.
    expect(screen.getByRole('dialog')).not.toHaveAttribute('aria-describedby');
  });

  it('closes on Escape', async () => {
    const { onClose } = open();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes from a close button that has an accessible name', async () => {
    const { onClose } = open();
    // Three of the seven close buttons in this app announced only "button".
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('traps Tab inside itself', async () => {
    render(
      <>
        <button type="button">behind the overlay</button>
        <Modal title="Labs" onClose={() => {}}>
          <Button>Start lab</Button>
        </Modal>
      </>,
    );

    // By text, not by role: the test above establishes that the overlay has
    // already removed this button from the accessibility tree. It is still a
    // real, focusable DOM node, which is exactly why the trap has to hold.
    const outside = screen.getByText('behind the overlay');
    expect(outside).toBeInstanceOf(HTMLButtonElement);

    const inside = [
      screen.getByRole('button', { name: 'Close' }),
      screen.getByRole('button', { name: 'Start lab' }),
    ];

    // Enough presses to wrap the trap more than once: a trap that merely
    // *started* focus inside would leak on the second lap.
    for (let i = 0; i < 6; i += 1) {
      await userEvent.tab();
      expect(document.activeElement).not.toBe(outside);
      expect(inside).toContain(document.activeElement);
    }
  });

  it('restores focus to the control that opened it', async () => {
    function Harness() {
      const [showing, setShowing] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setShowing(true)}>
            Browse library
          </button>
          {showing && (
            <Modal title="Library" onClose={() => setShowing(false)}>
              <Button>Load canvas</Button>
            </Modal>
          )}
        </>
      );
    }

    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Browse library' });

    await userEvent.click(opener);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await userEvent.keyboard('{Escape}');

    // Without restore, focus lands on `<body>` and the next Tab starts from the
    // top of the document — the user is thrown back to the beginning of the
    // page for having closed a dialog.
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it('renders a toolbar outside the scrolling body', () => {
    // `TemplateLibraryModal`'s filter row must not scroll away with the
    // results. Asserted structurally, because "it looks fine" is not something
    // jsdom can see: the toolbar is a sibling of the body, not inside it.
    open({ toolbar: <span>filters</span> });

    const toolbar = screen.getByText('filters').closest('.mb-modal__toolbar');
    expect(toolbar).not.toBeNull();
    expect(toolbar?.querySelector('.mb-modal__body')).toBeNull();
    expect(
      screen.getByRole('button', { name: 'Start lab' }).closest('.mb-modal__body'),
    ).not.toBeNull();
  });

  it('renders nothing when closed', () => {
    render(
      <Modal title="Library" onClose={() => {}} open={false}>
        <Button>Load canvas</Button>
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
