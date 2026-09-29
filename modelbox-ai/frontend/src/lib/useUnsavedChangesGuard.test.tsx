/**
 * The unsaved-changes guard asks before leaving (Sprint 8 Step 3): on an
 * in-app link, and on closing or reloading the page. It stays out of the way
 * when there is nothing unsaved, and a declined prompt keeps the user where
 * they are.
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LEAVE_PROMPT, useUnsavedChangesGuard } from '@/lib/useUnsavedChangesGuard';

function Page({ dirty }: { dirty: boolean }) {
  useUnsavedChangesGuard(dirty);
  return (
    <>
      <a href="/models">Models</a>
      <a href="https://example.com/elsewhere">Elsewhere</a>
    </>
  );
}

/** Click a link and report whether its default (the navigation) was prevented. */
function follow(name: string): boolean {
  const link = screen.getByRole('link', { name });
  const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
  link.dispatchEvent(event);
  return event.defaultPrevented;
}

afterEach(() => vi.restoreAllMocks());

describe('useUnsavedChangesGuard', () => {
  it('asks before following an in-app link, and stays when declined', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<Page dirty />);
    expect(follow('Models')).toBe(true);
    expect(confirm).toHaveBeenCalledWith(LEAVE_PROMPT);
  });

  it('leaves when the user agrees', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<Page dirty />);
    expect(follow('Models')).toBe(false);
  });

  it('negative control: with nothing unsaved it never asks', () => {
    const confirm = vi.spyOn(window, 'confirm');
    render(<Page dirty={false} />);
    expect(follow('Models')).toBe(false);
    expect(confirm).not.toHaveBeenCalled();
  });

  it('does not intercept a link to another site', () => {
    const confirm = vi.spyOn(window, 'confirm');
    render(<Page dirty />);
    follow('Elsewhere');
    expect(confirm).not.toHaveBeenCalled();
  });

  it('asks the browser to confirm closing or reloading the page', () => {
    render(<Page dirty />);
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('negative control: closing a saved page is not held up', () => {
    render(<Page dirty={false} />);
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it('stops asking once the page is saved', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { rerender } = render(<Page dirty />);
    rerender(<Page dirty={false} />);
    expect(follow('Models')).toBe(false);
    expect(confirm).not.toHaveBeenCalled();
  });
});
