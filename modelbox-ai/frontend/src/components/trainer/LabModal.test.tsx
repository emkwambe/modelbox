/**
 * The conversion, checked at the call site rather than only on the primitive.
 *
 * `ui/Modal.test.tsx` proves the dialog properties hold for a `Modal`. It
 * cannot prove this file *is* one — a modal that keeps its own `position:
 * fixed` div still renders, still lists labs, and still closes on a click. So
 * the properties are re-asserted here through the public surface: a dialog with
 * an accessible name, dismissable from the keyboard.
 *
 * The list is checked against `LABS` rather than against a count. A `length ===
 * 3` here would go green on a catalogue that had silently lost an entry, which
 * is a failure this repository has already shipped four times.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { LABS } from '@/content/trainer';

import LabModal from './LabModal';

describe('LabModal', () => {
  it('has labs to list', () => {
    // Precondition: an empty catalogue would make the breadth test below
    // iterate nothing and pass while listing no labs at all.
    expect(LABS.length).toBeGreaterThan(0);
  });

  it('is a dialog with an accessible name', () => {
    render(<LabModal onClose={() => {}} onSelect={() => {}} />);
    expect(
      screen.getByRole('dialog', { name: /Spot the Flaw — Labs/ }),
    ).toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    render(<LabModal onClose={onClose} onSelect={() => {}} />);

    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('offers every lab in the catalogue', () => {
    render(<LabModal onClose={() => {}} onSelect={() => {}} />);
    for (const lab of LABS) {
      expect(screen.getByText(lab.title)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('button', { name: /Start lab/ })).toHaveLength(
      LABS.length,
    );
  });

  it('starts the lab that was chosen', async () => {
    const onSelect = vi.fn();
    render(<LabModal onClose={() => {}} onSelect={onSelect} />);

    const starts = screen.getAllByRole('button', { name: /Start lab/ });
    await userEvent.click(starts[starts.length - 1]!);

    // The last one, not the first: an `onSelect` wired to a captured variable
    // outside the map would pass on the first row and fail here.
    expect(onSelect).toHaveBeenCalledWith(LABS[LABS.length - 1]);
  });
});
