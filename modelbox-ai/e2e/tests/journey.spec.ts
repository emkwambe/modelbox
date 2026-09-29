/**
 * One consultant engagement, end to end, in a real browser against the running
 * appliance (Sprint 8 Step 7). CI only: the "Engagement Journey" job starts the
 * appliance in configuration B and makes the owner with `create-owner`.
 *
 * Two paths, and the journey must pass both:
 *
 * - The genuine Oracle HR export: it reconciles, its fields can be verified,
 *   an edit lapses a verified field, and a drifted export of the same schema
 *   is reported drift by drift against the written rules.
 * - The documentation-derived Snowflake fixture: its import is unreconciled,
 *   the warning comes first, and the server refuses to verify its fields. This
 *   is the discrimination: the same assertions that pass for HR would fail
 *   here if the application let an unreconciled import through.
 *
 * Fixtures are read from the backend's test tree, the same files its own
 * tests use; nothing is copied.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';
import type { Download, Locator, Page } from '@playwright/test';

const FIXTURES = path.resolve(__dirname, '..', '..', 'backend', 'tests', 'fixtures');
const HR = path.join(FIXTURES, 'ddl', 'oracle', 'hr.sql');
const HR_DRIFTED = path.join(FIXTURES, 'ddl_drift', 'oracle', 'hr.sql');
const HR_DRIFTS = path.join(FIXTURES, 'ddl_drift', 'oracle', 'changes', 'hr.expected.json');
const ADVENTUREWORKS = path.join(FIXTURES, 'ddl', 'tsql', 'adventureworks.sql');
const SNOWFLAKE = path.join(FIXTURES, 'ddl', 'snowflake', 'ledger_schema.sql');

const GAPS_HEADER = '-- Export gaps (';

function required(name: string): string {
  const value = process.env[name];
  // Loud, not skipped: a journey that cannot sign in has verified nothing.
  if (!value) throw new Error(`${name} is not set; the journey runs against a real appliance`);
  return value;
}

interface Counts {
  verified: number;
  fields: number;
  pending: number;
}

function counts(statement: string | null): Counts {
  const m = /(\d+) of (\d+) fields verified, (\d+) pending review/.exec(statement ?? '');
  if (!m) throw new Error(`not a verification statement: ${statement}`);
  return { verified: Number(m[1]), fields: Number(m[2]), pending: Number(m[3]) };
}

async function text(download: Download): Promise<string> {
  return readFileSync(await download.path(), 'utf8');
}

async function signIn(page: Page) {
  // A save leaves nothing dirty, so this should never fire; if it does, the
  // navigation still happens and the assertion after it decides.
  page.on('dialog', (dialog) => void (dialog.type() === 'beforeunload' ? dialog.accept() : dialog.dismiss()));
  await page.goto('/import');
  await page.getByRole('main').getByRole('button', { name: 'Sign in' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Email').fill(required('E2E_EMAIL'));
  await dialog.getByLabel('Password').fill(required('E2E_PASSWORD'));
  await dialog.locator('form').getByRole('button', { name: 'Sign in' }).click();
  await expect(dialog).toBeHidden();
}

/** Import a file through /import and return the result section. */
async function importFile(page: Page, file: string, dialect: string, title: string): Promise<Locator> {
  await page.goto('/import');
  await expect(page.getByRole('button', { name: 'Import', exact: true })).toBeVisible();
  await page.getByLabel('Dialect of the file').selectOption(dialect);
  await page.getByLabel('Model title').fill(title);
  await page.getByLabel('DDL file').setInputFiles(file);
  await page.getByRole('button', { name: 'Import', exact: true }).click();
  const result = page.getByRole('region', { name: 'Import result' });
  await expect(result.getByRole('heading', { level: 2 })).toHaveText(title, { timeout: 120_000 });
  return result;
}

/** Open the imported model on the canvas and return its id. */
async function openOnCanvas(page: Page, result: Locator): Promise<string> {
  await result.getByRole('button', { name: 'Open on the canvas →' }).click();
  await page.waitForURL(/\/canvas\/[0-9a-f-]{36}$/);
  const id = page.url().split('/').pop()!;
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeEnabled();
  return id;
}

function node(page: Page, entity: string): Locator {
  return page.locator(`.react-flow__node[data-id="${entity}"]`);
}

function columnRow(page: Page, entity: string, column: string): Locator {
  // A row is two spans, the name (after any key markers) and the type; match
  // the name span, so COUNTRY does not match COUNTRY_ID.
  const name = page.locator('span').filter({ hasText: new RegExp(`^[^A-Za-z_]*${column}\\b`) });
  return node(page, entity).locator('li').filter({ has: name });
}

/** No two tables on the canvas overlap, measured in the browser. */
async function expectNoOverlap(page: Page, count: number) {
  const nodes = page.locator('.react-flow__node');
  await expect(nodes).toHaveCount(count);
  const boxes = await nodes.evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return { id: el.getAttribute('data-id'), x: r.x, y: r.y, w: r.width, h: r.height };
    }),
  );
  const overlapping = boxes.flatMap((a, i) =>
    boxes
      .slice(i + 1)
      .filter((b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h)
      .map((b) => `${a.id} and ${b.id}`),
  );
  expect(overlapping).toEqual([]);
}

/** The column editor sits over the canvas's lower left; close it before clicking a node. */
async function closeEditor(page: Page) {
  await page.getByRole('button', { name: 'Close', exact: true }).click();
}

async function save(page: Page) {
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('✓ Saved')).toBeVisible();
}

async function openDictionary(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: 'Dictionary', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Dictionary review' });
  await expect(panel.getByRole('status')).toHaveText(/fields verified/);
  return panel;
}

async function readCounts(panel: Locator): Promise<Counts> {
  return counts(await panel.getByRole('status').textContent());
}

async function exportDdl(page: Page, dialect: string): Promise<string> {
  await page.getByRole('button', { name: 'Export artifacts' }).click();
  await page.getByLabel('Artifact format').selectOption('ddl');
  await page.getByLabel('SQL dialect').selectOption(dialect);
  await page.getByRole('button', { name: 'Generate', exact: true }).click();
  const download = page.getByRole('button', { name: 'Download', exact: true });
  await expect(download).toBeEnabled({ timeout: 120_000 });
  const [file] = await Promise.all([page.waitForEvent('download'), download.click()]);
  return text(file);
}

interface ExpectedDrift {
  kind: string;
  table: string;
  column?: string;
  columns?: string[];
  class: string;
}

/** The "Where" cell the panel shows for an expected drift. */
function whereOf(d: ExpectedDrift): RegExp {
  const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  if (d.column) return new RegExp(`^${escape(`${d.table}.${d.column}`)}$`);
  if (d.columns) return new RegExp(`^${escape(`${d.table}(${d.columns.join(', ')})`)}$`);
  // A primary-key change names its table; the panel may add the key columns.
  return new RegExp(`^${escape(d.table)}(\\(.*\\))?$`);
}

test('the engagement journey on the genuine Oracle HR export', async ({ page }) => {
  await signIn(page);
  let modelId = '';

  await test.step('a. import the Oracle HR export: reconciled, zero gaps', async () => {
    const result = await importFile(page, HR, 'oracle', 'HR engagement');
    await expect(result).toContainText(
      'Reconciled: 7 tables and 10 relationships, every count matching the file.',
    );
    await expect(result.getByRole('heading', { name: 'Gaps' })).toHaveCount(0);
    const [file] = await Promise.all([
      page.waitForEvent('download'),
      result.getByRole('button', { name: 'Report (JSON)' }).click(),
    ]);
    const report = JSON.parse(await text(file));
    expect(report.status).toBe('reconciled');
    expect(report.reconciliation.gaps).toEqual([]);
    modelId = await openOnCanvas(page, result);
  });

  await test.step('b. a column business name and a table owner survive save and reload', async () => {
    await page.goto(`/canvas/${modelId}`);
    // An import stores no positions; the canvas lays the tables out on open.
    await expectNoOverlap(page, 7);
    await columnRow(page, 'LOCATIONS', 'CITY').click();
    await page.getByLabel('Business name', { exact: true }).fill('Office city');
    await closeEditor(page);
    await node(page, 'LOCATIONS').getByText('LOCATIONS', { exact: true }).click();
    await expect(page.getByText('Entity settings')).toBeVisible();
    await page.getByLabel('Business owner', { exact: true }).fill('Head of Facilities');
    await save(page);

    await page.reload();
    // The layout was saved with the edits.
    await expectNoOverlap(page, 7);
    await columnRow(page, 'LOCATIONS', 'CITY').click();
    await expect(page.getByLabel('Business name', { exact: true })).toHaveValue('Office city');
    await closeEditor(page);
    await node(page, 'LOCATIONS').getByText('LOCATIONS', { exact: true }).click();
    await expect(page.getByLabel('Business owner', { exact: true })).toHaveValue('Head of Facilities');
  });

  const businessName = 'LOCATIONS.CITY · business_name';
  let before: Counts;

  await test.step('c. the dictionary counts, and one field verified with its Verify button', async () => {
    const panel = await openDictionary(page);
    before = await readCounts(panel);
    expect(before.verified).toBe(0);
    expect(before.pending).toBe(before.fields);
    await panel.getByLabel('Table').selectOption('LOCATIONS');
    await expect(panel.getByLabel(`Status of ${businessName}`)).toHaveText('pending review');

    await panel.getByRole('button', { name: `Verify ${businessName}` }).click();
    const results = panel.getByLabel('Verification results');
    await expect(results).toContainText(`${businessName}: verified`);
    await expect(results).toContainText('Reconciled import: yes');
    await expect(results).toContainText('Definition (ISO/IEC 11179-4): passes');
    await expect(results).toContainText('Provenance: person (can support verified)');
    await expect(panel.getByLabel(`Status of ${businessName}`)).toHaveText('verified');
    await expect(panel.getByRole('status')).toHaveText(
      `1 of ${before.fields} fields verified, ${before.fields - 1} pending review`,
    );
  });

  await test.step('d. editing the verified value drops it back to pending', async () => {
    await page.getByRole('button', { name: 'Hide dictionary' }).click();
    await columnRow(page, 'LOCATIONS', 'CITY').click();
    await page.getByLabel('Business name', { exact: true }).fill('Site city');
    await save(page);

    const panel = await openDictionary(page);
    await panel.getByLabel('Table').selectOption('LOCATIONS');
    await expect(panel.getByLabel(`Status of ${businessName}`)).toHaveText('pending review');
    await expect(panel.getByRole('button', { name: `Verify ${businessName}` })).toBeVisible();
    await expect(panel.getByRole('status')).toHaveText(
      `0 of ${before.fields} fields verified, ${before.fields} pending review`,
    );
  });

  await test.step('e. the drifted export: each drift classified, the verified field flagged', async () => {
    // CITY's type is what the drifted export widens; verify it first, through
    // the selection control, so the drift has a verified field to flag.
    const dictionary = page.getByRole('region', { name: 'Dictionary review' });
    const dataType = 'LOCATIONS.CITY · data_type';
    await dictionary.getByLabel(`Select ${dataType}`).check();
    await dictionary.getByRole('button', { name: 'Verify selected (1)' }).click();
    await expect(dictionary.getByLabel(`Status of ${dataType}`)).toHaveText('verified');

    await page.getByRole('button', { name: 'Drift report', exact: true }).click();
    const panel = page.getByRole('region', { name: 'Drift report' });
    await panel.getByLabel('Deployed schema DDL file').setInputFiles(HR_DRIFTED);
    await panel.getByLabel('Dialect of the file').selectOption('oracle');
    await panel.getByRole('button', { name: 'Compare' }).click();
    const result = panel.getByLabel('Drift report result');
    await expect(result).toBeVisible({ timeout: 120_000 });

    // Both sides are reconciled imports: no warning.
    await expect(result.getByRole('alert')).toHaveCount(0);

    const manifest = JSON.parse(readFileSync(HR_DRIFTS, 'utf8')) as {
      drifts: ExpectedDrift[];
      possible_renames: { table: string; removed: string; added: string }[];
    };
    const expected = manifest.drifts;
    const tally = (cls: string) => expected.filter((d) => d.class === cls).length;
    await expect(result).toContainText(
      `Drifts: ${expected.length} — ${tally('breaking')} breaking, ${tally('non-breaking')} non-breaking, ` +
        `${tally('informational')} informational; 1 touch a verified field`,
    );

    const rows = await result.locator('tbody tr').evaluateAll((trs) =>
      trs.map((tr) => Array.from(tr.querySelectorAll('td'), (td) => td.textContent ?? '')),
    );
    expect(rows).toHaveLength(expected.length);
    for (const d of expected) {
      const kind = d.kind.replace(/_/g, ' ');
      const where = whereOf(d);
      const match = rows.filter(([, , k, w]) => k === kind && where.test(w));
      expect(match, `${d.kind} ${where}`).toHaveLength(1);
      const [cls, rule, , , flag] = match[0];
      expect(cls, `${d.kind} ${where}`).toBe(d.class);
      expect(rule, `${d.kind} ${where} names its rule`).toMatch(/^D\d+$/);
      if (d.kind === 'type_changed' && d.table === 'LOCATIONS' && d.column === 'CITY') {
        expect(flag).toBe('verified field affected by drift: LOCATIONS.CITY.data_type');
      } else {
        expect(flag, `${d.kind} ${where} touches no verified field`).toBe('');
      }
    }
    for (const r of manifest.possible_renames) {
      await expect(result).toContainText(`${r.table}: ${r.removed} removed and ${r.added} added`);
    }
  });

  await test.step('f. PostgreSQL DDL: HR states everything, AdventureWorks names its gaps', async () => {
    const hr = await exportDdl(page, 'postgres');
    expect(hr).toMatch(/CREATE TABLE/i);
    expect(hr).not.toContain(GAPS_HEADER);

    const result = await importFile(page, ADVENTUREWORKS, 'tsql', 'AdventureWorks engagement');
    await expect(result).toContainText('Reconciled:');
    await openOnCanvas(page, result);
    const aw = await exportDdl(page, 'postgres');
    expect(aw).toContain(GAPS_HEADER);
    expect(aw).toContain('what the model holds that this file does not state.');
    expect(aw).toContain('computed_column');
  });
});

test('a documentation-derived Snowflake import stays unreconciled and cannot be verified', async ({ page }) => {
  await signIn(page);

  const result = await importFile(page, SNOWFLAKE, 'snowflake', 'Ledger (documentation-derived)');
  // The first thing after the title is the warning, not the counts.
  await expect(result.locator('h2 + *')).toHaveText(/^Unreconciled: /);
  await expect(result.getByRole('heading', { name: 'Gaps' })).toBeVisible();
  await openOnCanvas(page, result);

  const panel = await openDictionary(page);
  const start = await readCounts(panel);
  expect(start.verified).toBe(0);
  const fields = panel.getByRole('list', { name: 'Dictionary fields' });
  await fields.getByRole('button', { name: /^Verify / }).first().click();
  const results = panel.getByLabel('Verification results');
  await expect(results).toContainText('Reconciled import: no');
  await expect(results).toContainText('Stayed pending review because the model is not a reconciled import');
  await expect(panel.getByRole('status')).toHaveText(
    `0 of ${start.fields} fields verified, ${start.fields} pending review`,
  );

  // The drift report says so first, too.
  await page.getByRole('button', { name: 'Drift report', exact: true }).click();
  const drift = page.getByRole('region', { name: 'Drift report' });
  await drift.getByLabel('Deployed schema DDL file').setInputFiles(SNOWFLAKE);
  await drift.getByLabel('Dialect of the file').selectOption('snowflake');
  await drift.getByRole('button', { name: 'Compare' }).click();
  const report = drift.getByLabel('Drift report result');
  await expect(report).toBeVisible({ timeout: 120_000 });
  const first = report.locator('> *').first();
  await expect(first).toHaveAttribute('role', 'alert');
  await expect(first).toContainText('Unreconciled import.');
});
