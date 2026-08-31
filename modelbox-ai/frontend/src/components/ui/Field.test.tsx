/**
 * Field — the label/control association, which is the whole reason it exists.
 *
 * `htmlFor` appears once in the rest of this frontend. Everywhere else a label
 * is a `<div>` above an input, so clicking it does nothing and a screen reader
 * reaches an unnamed control.
 *
 * The error test resolves `aria-describedby` through the document rather than
 * comparing strings. That distinction matters: an attribute pointing at an id
 * that does not exist is announced as nothing, and a string comparison passes
 * on it happily.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import Field, { Input, Select, Textarea } from './Field';

describe('Field', () => {
  it('names its control, so the label reaches it', () => {
    render(
      <Field label="Workspace">
        <Input />
      </Field>,
    );
    // Fails if `useId` is not wired through to both `htmlFor` and `id`.
    expect(screen.getByLabelText('Workspace')).toBeInstanceOf(HTMLInputElement);
  });

  it('focuses the control when the label is clicked', async () => {
    render(
      <Field label="Connection name">
        <Input />
      </Field>,
    );

    await userEvent.click(screen.getByText('Connection name'));
    expect(screen.getByLabelText('Connection name')).toHaveFocus();
  });

  it.each([
    ['input', <Input key="i" />],
    ['select', <Select key="s" />],
    ['textarea', <Textarea key="t" />],
  ])('wires a %s the same way', (_name, control) => {
    render(<Field label="Value">{control}</Field>);
    expect(screen.getByLabelText('Value')).toBeInTheDocument();
  });

  it('describes the control with its error, by a resolvable id', () => {
    render(
      <Field label="Password" error="Must be at least 12 characters.">
        <Input />
      </Field>,
    );

    const control = screen.getByLabelText('Password');
    expect(control).toHaveAttribute('aria-invalid', 'true');

    const describedBy = control.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();

    // The assertion a string comparison would miss: the id has to point at
    // something that exists and says the right thing.
    const description = document.getElementById(describedBy ?? '');
    expect(description).not.toBeNull();
    expect(description?.textContent).toBe('Must be at least 12 characters.');
  });

  it('announces the error rather than only colouring it', () => {
    render(
      <Field label="Password" error="Too short.">
        <Input />
      </Field>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Too short.');
  });

  it('omits aria-describedby when there is nothing to describe', () => {
    // The precondition for the resolve test above. If the attribute were always
    // present, that test could be passing on a stale or empty value rather than
    // on the error actually being wired.
    render(
      <Field label="Password">
        <Input />
      </Field>,
    );
    expect(screen.getByLabelText('Password')).not.toHaveAttribute(
      'aria-describedby',
    );
  });

  it('associates a description as well as an error', () => {
    render(
      <Field
        label="Expiry"
        description="Leave blank for a key that never expires."
        error="Not a valid date."
      >
        <Input />
      </Field>,
    );

    const control = screen.getByLabelText('Expiry');
    const ids = (control.getAttribute('aria-describedby') ?? '').split(' ');
    expect(ids).toHaveLength(2);

    const text = ids
      .map((id) => document.getElementById(id)?.textContent)
      .join(' ');
    expect(text).toContain('never expires');
    expect(text).toContain('Not a valid date.');
  });

  it('marks a required control required on the control itself', () => {
    // The asterisk is `aria-hidden`, so it is decoration. Without the attribute
    // on the control, "required" would be a purely visual claim.
    render(
      <Field label="Name" required>
        <Input />
      </Field>,
    );

    // Queried by accessible name rather than by label text, which is the
    // stronger assertion: the accessible-name computation skips `aria-hidden`
    // content, so this passing proves the decorative asterisk does not end up
    // in the control's announced name as "Name *".
    const control = screen.getByRole('textbox', { name: 'Name' });
    expect(control).toBeRequired();
  });
});
