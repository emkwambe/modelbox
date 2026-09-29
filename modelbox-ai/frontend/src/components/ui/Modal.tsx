'use client';

/**
 * The dialog.
 *
 * Three modals ship today — `TemplateLibraryModal`, `LabModal`, `AuthModal` —
 * and all three are a `position: fixed` div with an `onClick` on the scrim.
 * Between them they are missing every property a dialog is supposed to have:
 *
 * - **No focus trap.** Tab walks straight out of the dialog and into the page
 *   behind it, which is still fully interactive.
 * - **No Escape.** The only dismissal is a mouse click.
 * - **No `role="dialog"` and no `aria-modal`,** so assistive technology is not
 *   told the rest of the page is inert, and the dialog is not announced.
 * - **No accessible name.** The heading is a `<div>` with a bold weight.
 * - **No focus restore.** After closing, focus is on `<body>` and the next Tab
 *   starts from the top of the document.
 * - `AuthModal` has no close button at all: a keyboard user who opens it
 *   cannot get out of it.
 *
 * None of that is written here. It comes from `@radix-ui/react-dialog`, which
 * has been in `package.json` and unused since the frontend was scaffolded. The
 * job of this file is to make the correct dialog the *easy* one to reach for,
 * so the properties hold at every call site rather than at whichever one
 * someone remembered.
 *
 * **Mounted means open.** All three call sites render `{show && <XModal …/>}`,
 * so `open` defaults to true and the component reads the same way the code it
 * replaces did. `open` is still a prop because a caller that wants Radix's
 * controlled behaviour should not have to unmount to get it.
 */

import * as Dialog from '@radix-ui/react-dialog';
import { useLayoutEffect as useRadixLayoutEffect } from '@radix-ui/react-use-layout-effect';
import { useRef } from 'react';
import type { ReactNode } from 'react';

import CloseButton from './CloseButton';

interface ModalProps {
  /**
   * The accessible name, and the visible heading. Required, because a dialog
   * without one is announced as "dialog" and nothing else — and because Radix
   * warns about it at runtime, which is a warning nobody reads.
   */
  title: ReactNode;
  /** The subheading. Wired to `aria-describedby` by Radix when present. */
  description?: ReactNode;
  onClose: () => void;
  open?: boolean;
  /**
   * The dialog's width, as a CSS length. The three call sites want 920px,
   * 760px and 380px, so this is a real axis rather than a t-shirt size that
   * would have three values and one call site each.
   */
  width?: string;
  /**
   * A fixed strip below the header — filters, tabs — that must not scroll with
   * the body. `TemplateLibraryModal`'s search and facet row is exactly this,
   * and folding it into `children` would make it scroll away.
   */
  toolbar?: ReactNode;
  children: ReactNode;
  closeLabel?: string;
}

export default function Modal({
  title,
  description,
  onClose,
  open = true,
  width = 'min(560px, 100%)',
  toolbar,
  children,
  closeLabel,
}: ModalProps) {
  /*
   * Focus restore, which Radix will not do for these call sites.
   *
   * A modal `Dialog` prevents the default close-autofocus and focuses
   * `Dialog.Trigger` instead — and there is no trigger here, because all three
   * call sites open the dialog from their own state rather than from a Radix
   * control. So the restore silently resolves to nothing and focus lands on
   * `<body>`: the user closes a dialog and the next Tab starts from the top of
   * the page. Verified against the real component before writing this, not
   * assumed from the docs.
   *
   * The opener is captured in a *layout* effect on purpose. Layout effects
   * flush before every passive effect in the commit, and `FocusScope` moves
   * focus into the dialog from a passive one — capture it any later and the
   * element recorded is the dialog's own first control, which restores focus to
   * a node that is about to be removed.
   */
  const openerRef = useRef<HTMLElement | null>(null);
  useRadixLayoutEffect(() => {
    if (open) openerRef.current = document.activeElement as HTMLElement | null;
  }, [open]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="mb-modal__scrim" />
        <Dialog.Content
          className="mb-modal"
          style={{ width }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            openerRef.current?.focus();
          }}
          // Radix points `aria-describedby` at its `Dialog.Description` and
          // warns when there is none. The opt-out is passing the attribute
          // explicitly as `undefined` — which has to be *conditional*, because
          // props spread over Radix's own value: passing it unconditionally
          // would strip the association from every dialog that does have a
          // description, leaving an attribute-shaped hole nothing announces.
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <div className="mb-modal__header">
            <div>
              <Dialog.Title className="mb-modal__title">{title}</Dialog.Title>
              {description && (
                <Dialog.Description className="mb-modal__description">
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <CloseButton label={closeLabel} />
            </Dialog.Close>
          </div>

          {toolbar && <div className="mb-modal__toolbar">{toolbar}</div>}

          <div className="mb-modal__body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
