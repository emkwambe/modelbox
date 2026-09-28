/**
 * The conversion, checked at the call site.
 *
 * This is the modal that had no way out. No Escape, no close button, and no
 * focus trap — so a keyboard user who opened it either signed in or reloaded
 * the page. The first three tests are that defect, one assertion each.
 *
 * The rest are the form: the controls are named, the two modes differ, and a
 * failed sign-in is *announced* rather than only coloured. That last one is the
 * F3 half of this commit — the error line was `#dc2626`, Tailwind's red, in a
 * codebase whose brand error colour is something else entirely.
 *
 * Measured against the pre-conversion component, 2026-08-31: six of these nine
 * fail and three pass. The six are the properties that did not exist — dialog
 * role and name, Escape, a close button, the pressed state on the mode
 * toggles, and `aria-live` on the error. The three that pass on both are the
 * behaviour — the controls were already implicitly labelled by their wrapping
 * `<label>`, submit was already gated, and Dev Quick Login already worked — so
 * the suite says the conversion added those six without disturbing these three.
 *
 * Dev Quick Login was removed in Sprint 7: it signed in with a password
 * published in this repository, from the production bundle. The last block
 * fails if it, or the credentials it used, come back.
 */

import { readFileSync } from 'node:fs';

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SRC, isTest, relative, stripComments, walk } from '@/test/sourceWalk';

import AuthModal from './AuthModal';

const { login, register } = vi.hoisted(() => ({
  login: vi.fn(),
  register: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ login, register }));

beforeEach(() => {
  login.mockReset().mockResolvedValue('a-token');
  register.mockReset().mockResolvedValue('a-token');
});

/**
 * The form's submit button. Disambiguated by `type`, because the sign-in tab
 * and the submit button legitimately carry the same accessible name — and a
 * query that resolved to the tab would report an always-enabled control and
 * make the disabled-until-valid test meaningless.
 */
const submitButton = (): HTMLElement =>
  screen
    .getAllByRole('button', { name: /^(Sign in|Signing in…)$/ })
    .find((b) => b.getAttribute('type') === 'submit')!;

/** A mode toggle, which is the button carrying a pressed state. */
const modeTab = (name: string): HTMLElement =>
  screen
    .getAllByRole('button', { name })
    .find((b) => b.hasAttribute('aria-pressed'))!;

describe('AuthModal', () => {
  it('is a dialog with an accessible name', () => {
    render(<AuthModal onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'ModelBox AI' })).toBeInTheDocument();
  });

  it('can be closed from the keyboard', async () => {
    // The defect this conversion exists for: before it there was no Escape
    // handler and no close control of any kind, so opening this modal was a
    // one-way door for anyone not using a mouse.
    const onClose = vi.fn();
    render(<AuthModal onClose={onClose} />);

    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('has a close button with an accessible name', async () => {
    const onClose = vi.fn();
    render(<AuthModal onClose={onClose} />);

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('names its controls', () => {
    render(<AuthModal onClose={() => {}} />);
    expect(screen.getByLabelText('Email')).toBeInstanceOf(HTMLInputElement);
    expect(screen.getByLabelText('Password')).toBeInstanceOf(HTMLInputElement);
  });

  it('announces which mode is selected, not just colours it', () => {
    render(<AuthModal onClose={() => {}} />);
    // The active tab was distinguished by a blue underline and blue text and
    // nothing else, which is state carried by colour alone.
    expect(modeTab('Sign in')).toHaveAttribute('aria-pressed', 'true');
    expect(modeTab('Create account')).toHaveAttribute('aria-pressed', 'false');
  });

  it('reveals the name field only when creating an account', async () => {
    render(<AuthModal onClose={() => {}} />);
    expect(screen.queryByLabelText(/Full name/)).toBeNull();

    await userEvent.click(modeTab('Create account'));
    expect(screen.getByLabelText(/Full name/)).toBeInstanceOf(HTMLInputElement);
  });

  it('will not submit without credentials, and will with them', async () => {
    render(<AuthModal onClose={() => {}} />);

    // Both halves, because a control that is disabled unconditionally satisfies
    // the first assertion on its own and tells you nothing.
    expect(submitButton()).toBeDisabled();

    await userEvent.type(screen.getByLabelText('Email'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('Password'), 'hunter2hunter2');
    expect(submitButton()).toBeEnabled();
  });

  it('announces a failed sign-in rather than only colouring it', async () => {
    login.mockRejectedValueOnce(new Error('nope'));
    render(<AuthModal onClose={() => {}} />);

    await userEvent.type(screen.getByLabelText('Email'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password');
    await userEvent.click(submitButton());

    // By role, not by text: the point is that it reaches a screen reader.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Sign-in failed. Check your credentials.');
    expect(alert).toHaveAttribute('aria-live', 'assertive');
  });

});

/** The published development credentials. Code must not carry either. */
const DEV_CREDENTIALS = ['dev@modelbox.ai', 'password123'];

/** `file: credential` for every non-test source that carries one in code. */
function findDevCredentials(files: Record<string, string>): string[] {
  return Object.entries(files).flatMap(([path, source]) => {
    const code = stripComments(source);
    return DEV_CREDENTIALS.filter((cred) => code.includes(cred)).map(
      (cred) => `${path}: ${cred}`,
    );
  });
}

const appSources = (): Record<string, string> =>
  Object.fromEntries(
    walk(SRC)
      .filter((path) => !isTest(path))
      .map((path) => [relative(path), readFileSync(path, 'utf-8')]),
  );

describe('no development login', () => {
  it('offers no one-click development sign-in', () => {
    render(<AuthModal onClose={() => {}} />);
    expect(screen.queryByRole('button', { name: /dev|quick login/i })).toBeNull();
  });

  it('no application source carries the development credentials', () => {
    const files = appSources();
    // Precondition: the walk found the app, including this component.
    expect(Object.keys(files)).toContain('components/auth/AuthModal.tsx');
    expect(findDevCredentials(files)).toEqual([]);
  });

  it('negative control: the removed constants fail the check', () => {
    const files = {
      ...appSources(),
      'components/auth/AuthModal.tsx': "const DEV_PASSWORD = 'password123';\n",
    };
    expect(findDevCredentials(files)).toEqual([
      'components/auth/AuthModal.tsx: password123',
    ]);
  });
});
