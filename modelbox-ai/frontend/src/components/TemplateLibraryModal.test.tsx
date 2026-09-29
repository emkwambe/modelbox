/**
 * The conversion, checked at the call site.
 *
 * The dialog properties and the existing behaviour are asserted separately, so
 * the suite says both "this is a dialog now" and "it still does what it did".
 *
 * **Honest limit, unlike `LabModal.test.tsx`.** That file doubles as a
 * before/after: run against the pre-conversion component, exactly its two
 * dialog tests fail and its three behaviour tests pass, which is what proves
 * the behaviour survived. This suite cannot do that. The title queries are
 * scoped through `.mb-modal__body` — they have to be, because a domain facet
 * carries the same text as a template title — and that class does not exist on
 * the old component, so eight of the ten fail there for a reason that says
 * nothing about behaviour. Four of them are genuinely new properties (dialog,
 * Escape, named filter controls, toolbar placement); the rest are a regression
 * net from here on, not evidence about the conversion.
 *
 * The filter tests are the ones worth reading. The toolbar is the reason
 * `Modal` has a slot for it at all — filters that scroll away with the results
 * are a defect you cannot see in jsdom — so the structural assertion here is
 * that the controls are *outside* the scrolling body.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TEMPLATES } from '@/lib/templates';

import TemplateLibraryModal from './TemplateLibraryModal';

function open(props: Partial<React.ComponentProps<typeof TemplateLibraryModal>> = {}) {
  const onClose = vi.fn();
  const onLoadGraph = vi.fn();
  render(
    <TemplateLibraryModal
      onClose={onClose}
      onLoadGraph={onLoadGraph}
      {...props}
    />,
  );
  return { onClose, onLoadGraph };
}

/**
 * The results region, which is what the title queries below have to be scoped
 * to. Unscoped they are ambiguous: a domain facet in the toolbar carries the
 * same text as one of the template titles, so `getByText` matches an `<option>`
 * as well as a card — and the filter test would then "find" a template it had
 * just filtered out, in a dropdown that never filters.
 */
const results = (): HTMLElement =>
  screen.getByRole('dialog').querySelector('.mb-modal__body') as HTMLElement;

describe('TemplateLibraryModal', () => {
  it('has templates to list', () => {
    // Precondition for every breadth assertion below.
    expect(TEMPLATES.length).toBeGreaterThan(1);
  });

  it('is a dialog with an accessible name', () => {
    open();
    expect(
      screen.getByRole('dialog', { name: /Business Requirements Library/ }),
    ).toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const { onClose } = open();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('names its filter controls', () => {
    open();
    // Three unlabelled controls before this: a placeholder is not an
    // accessible name, and a bare `<select>` is announced as "combo box".
    expect(screen.getByRole('textbox', { name: 'Search templates' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by domain' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by paradigm' })).toBeInTheDocument();
  });

  it('keeps the filters out of the scrolling body', () => {
    open();
    // The whole reason `Modal` has a toolbar slot. Structural, because "the
    // filters scrolled away" is not something jsdom can observe.
    const search = screen.getByRole('textbox', { name: 'Search templates' });
    expect(search.closest('.mb-modal__toolbar')).not.toBeNull();
    expect(search.closest('.mb-modal__body')).toBeNull();
  });

  it('offers every template', () => {
    open();
    for (const template of TEMPLATES) {
      expect(within(results()).getByText(template.title)).toBeInTheDocument();
    }
  });

  it('filters the list by the search box', async () => {
    open();
    const target = TEMPLATES[0]!;
    const other = TEMPLATES.find((t) => t.title !== target.title);
    expect(other, 'need a second template for the filter to exclude').toBeDefined();

    await userEvent.type(
      screen.getByRole('textbox', { name: 'Search templates' }),
      target.title,
    );

    expect(within(results()).getByText(target.title)).toBeInTheDocument();
    // The half that makes it a filter test rather than a rendering test: it has
    // to remove something as well as keep something.
    expect(within(results()).queryByText(other!.title)).toBeNull();
  });

  it('says so when nothing matches', async () => {
    open();
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Search templates' }),
      'zzzzz-no-such-template',
    );
    expect(within(results()).getByText('No templates match your filters.')).toBeInTheDocument();
  });

  it('loads the template that was chosen', async () => {
    const { onLoadGraph } = open();
    const last = TEMPLATES[TEMPLATES.length - 1]!;

    const card = within(results()).getByText(last.title).closest('div')!.parentElement!;
    await userEvent.click(
      within(card).getByRole('button', { name: /Load canvas/ }),
    );

    // The last card, not the first: a handler closed over a variable outside
    // the map passes on the first row and fails on any other.
    expect(onLoadGraph).toHaveBeenCalledWith(last);
  });

  it('offers "Use prompt" only where there is a prompt bar to fill', () => {
    open();
    // Trainer has no prompt bar, so the callback is optional and the button
    // must not appear without it — otherwise it is a control that does nothing.
    expect(screen.queryByRole('button', { name: /Use prompt/ })).toBeNull();

    open({ onUsePrompt: vi.fn() });
    expect(screen.getAllByRole('button', { name: /Use prompt/ }).length).toBe(
      TEMPLATES.length,
    );
  });
});
