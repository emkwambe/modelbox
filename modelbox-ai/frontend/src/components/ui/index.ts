/**
 * The component layer's single entry point.
 *
 * Call sites import from `@/components/ui` and nothing else, so adopting a
 * primitive in a file is one import line rather than one per component.
 *
 * `ui.contract.test.tsx` discovers what this barrel exports and asserts a
 * fixture exists for each — so a primitive added here without a test fails, and
 * so does one removed from here while a test still names it.
 */

export { default as Badge, toneColor, toneTint } from './Badge';
export type { BadgeTone, BadgeVariant, Ground } from './Badge';

export { default as Banner } from './Banner';

export { default as Button } from './Button';
export type { ButtonSize, ButtonVariant } from './Button';

export { default as CloseButton } from './CloseButton';

export { default as Field, Input, Select, Textarea } from './Field';

export { default as Modal } from './Modal';

export { default as StatusText } from './StatusText';
