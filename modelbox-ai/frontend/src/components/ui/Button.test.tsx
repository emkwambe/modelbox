/**
 * Button — the behaviours, not the styling.
 *
 * Each of these fails for exactly one reason, noted where it is not obvious.
 * The styling is asserted structurally in `ui.css.test.ts`; jsdom cannot match
 * `:focus-visible` in `getComputedStyle`, so nothing here claims a focus ring
 * is painted.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Button from './Button';

const VARIANTS = ['primary', 'secondary', 'ghost', 'danger'] as const;

describe('Button', () => {
  it('has variants to check', () => {
    expect(VARIANTS.length).toBeGreaterThan(1);
  });

  it.each(VARIANTS)('%s renders a button with its label as the name', (variant) => {
    render(<Button variant={variant}>Export</Button>);
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('does not submit the form it sits in', async () => {
    // Mutation: removing `type = 'button'` from the default fails this test and
    // nothing else. The HTML default is `submit`, so a button placed in a form
    // for any other purpose silently submits it — a live bug, not a style
    // preference, and invisible until a form happens to wrap one.
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button>Add a row</Button>
      </form>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Add a row' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('still submits when asked to', () => {
    // The precondition for the test above: if `type` were ignored entirely
    // rather than defaulted, that test would pass for the wrong reason.
    render(<Button type="submit">Sign in</Button>);
    expect(screen.getByRole('button', { name: 'Sign in' })).toHaveAttribute(
      'type',
      'submit',
    );
  });

  it('ignores clicks when disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Save
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Save' });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    // The attribute alone is not the claim. A control that looks disabled and
    // still fires is the failure worth catching.
    expect(onClick).not.toHaveBeenCalled();
  });

  it('is busy and unclickable while loading', async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Signing in…
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Signing in…' });
    expect(button).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('announces a toggle rather than only colouring it', () => {
    // Four spellings of "this toggle is active" existed across the call sites,
    // every one of them colour-only — invisible to a screen reader and to
    // anyone who cannot distinguish the two shades.
    const { rerender } = render(<Button pressed={false}>Grid</Button>);
    expect(screen.getByRole('button', { name: 'Grid' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    rerender(<Button pressed>Grid</Button>);
    expect(screen.getByRole('button', { name: 'Grid' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('gives an icon-only button an accessible name', () => {
    // Three of the seven close buttons in the app announced only "button".
    // The union type makes omitting the label a compile error; this checks the
    // label actually reaches the accessible name rather than sitting unused.
    render(
      <Button iconOnly aria-label="Remove column">
        <span aria-hidden="true">✕</span>
      </Button>,
    );
    expect(
      screen.getByRole('button', { name: 'Remove column' }),
    ).toBeInTheDocument();
  });

  it('applies a tone without overriding the padding the stylesheet owns', () => {
    // `tone` has to be an inline style — it is a runtime value — so the risk is
    // that it becomes the wedge through which inline styling returns. It sets a
    // custom property and nothing else.
    render(<Button tone="#9333EA">Data Vault</Button>);
    const button = screen.getByRole('button', { name: 'Data Vault' });

    expect(button.style.getPropertyValue('--mb-btn-tone')).toBe('#9333EA');
    expect(button.style.padding).toBe('');
    expect(button.style.background).toBe('');
  });
});
