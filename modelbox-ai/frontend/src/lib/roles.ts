/**
 * The workspace role ladder, lowest first, as the API defines it
 * (`backend/app/api/v1/dependencies.py`, `_ROLE_LEVEL`).
 */
export const ROLE_LADDER = ['VIEWER', 'MEMBER', 'APPROVER', 'ADMIN', 'OWNER'] as const;

export type Role = (typeof ROLE_LADDER)[number];

/**
 * The API-key caps a creator may choose: every role up to their own, never
 * above it. An unknown role offers nothing, so the page cannot offer a cap it
 * cannot justify. The server refuses a higher cap regardless (Sprint 7, Step
 * 2.3); this keeps the page from offering one.
 */
export function capsUpTo(role: string | null | undefined): Role[] {
  const index = ROLE_LADDER.indexOf(role as Role);
  return index < 0 ? [] : ROLE_LADDER.slice(0, index + 1);
}
