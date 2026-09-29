'use client';

/**
 * A labelled form control.
 *
 * `htmlFor` appears **once** in this entire frontend. Every other label is a
 * `<div>` or a `<span>` sitting above an input with nothing connecting the two,
 * so clicking the label does nothing and a screen reader reaches the control
 * with no name. This component is what fixes that at every site it is adopted
 * at, because the association is not something the call site can forget to
 * write — `Field` owns the id.
 *
 * The control components below are deliberately near-empty. The four style
 * constants they replace were already shared between `input` and `select`
 * elements, so the split by element name was fiction; the shape is one class.
 */

import type {
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { cloneElement, useId } from 'react';

function classes(...names: (string | undefined | false)[]): string {
  return names.filter(Boolean).join(' ');
}

export function Input({
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={classes('mb-control', className)} />;
}

export function Select({
  className,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...rest} className={classes('mb-control', className)} />;
}

export function Textarea({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={classes('mb-control', className)} />;
}

interface FieldProps {
  label: string;
  /** Helper text. Associated with the control, so it is announced with it. */
  description?: ReactNode;
  /** When set, the control is marked invalid and described by this message. */
  error?: ReactNode;
  required?: boolean;
  /** The control. Its `id` and ARIA wiring are supplied here, not by the caller. */
  children: ReactElement<Record<string, unknown>>;
}

export default function Field({
  label,
  description,
  error,
  required,
  children,
}: FieldProps) {
  const id = useId();
  const describedBy = [
    description ? `${id}-description` : null,
    error ? `${id}-error` : null,
  ].filter(Boolean);

  return (
    <div className="mb-field">
      <label className="mb-field__label" htmlFor={id}>
        {label}
        {required ? (
          <span aria-hidden="true" className="mb-field__required">
            {' '}
            *
          </span>
        ) : null}
      </label>

      {cloneElement(children, {
        id,
        required,
        'aria-invalid': error ? true : undefined,
        // Omitted rather than empty when there is nothing to point at: a
        // dangling `aria-describedby` is announced as nothing and hides the
        // absence of a real description.
        'aria-describedby': describedBy.length ? describedBy.join(' ') : undefined,
      })}

      {description ? (
        <span className="mb-field__description" id={`${id}-description`}>
          {description}
        </span>
      ) : null}

      {error ? (
        <span className="mb-field__error" id={`${id}-error`} role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
