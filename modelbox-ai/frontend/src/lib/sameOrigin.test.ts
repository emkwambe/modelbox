/**
 * The UI reaches the backend on its own origin, never by a built-in address.
 *
 * The appliance publishes only the UI's port. That works because the browser
 * calls `/api/v1` on the UI's origin and the Next.js server forwards `/api/*`
 * to `modelbox-backend` over the compose network. Two things have to hold:
 * the client's base URL carries no scheme or host, and the rewrite forwards to
 * the compose service. The negative control hands the same check an absolute
 * base URL, the shape this replaced, and asserts it fails.
 */
import { describe, expect, it } from 'vitest';

import nextConfig from '../../next.config.js';
import { API_BASE_PATH, apiClient } from './api';

function checkSameOrigin(baseURL: string | undefined): void {
  if (baseURL === undefined) throw new Error('no base URL configured');
  if (/^[a-z][a-z0-9+.-]*:/i.test(baseURL) || baseURL.startsWith('//')) {
    throw new Error(`base URL names an origin: ${baseURL}`);
  }
  if (!baseURL.startsWith('/api/')) {
    throw new Error(`base URL is not under /api/: ${baseURL}`);
  }
}

describe('same-origin API', () => {
  it('the client calls /api/v1 on its own origin', () => {
    expect(API_BASE_PATH).toBe('/api/v1');
    expect(apiClient.defaults.baseURL).toBe(API_BASE_PATH);
    expect(() => checkSameOrigin(apiClient.defaults.baseURL)).not.toThrow();
  });

  it('the server forwards /api/* to the backend service', async () => {
    // Precondition: the default is what the image carries, so no override here.
    expect(process.env.MODELBOX_BACKEND_URL).toBeUndefined();
    const rewrites = await nextConfig.rewrites();
    expect(rewrites).toEqual([
      { source: '/api/health', destination: 'http://modelbox-backend:8000/health' },
      { source: '/api/:path*', destination: 'http://modelbox-backend:8000/api/:path*' },
    ]);
  });

  it('the health probe is matched before the catch-all', async () => {
    // Order is the whole rule: after /api/:path* it would be forwarded to
    // /api/health on the backend, which does not exist.
    const sources = (await nextConfig.rewrites()).map((r) => r.source);
    expect(sources.indexOf('/api/health')).toBeLessThan(sources.indexOf('/api/:path*'));
  });

  it('nothing inlines a backend address into the client bundle', () => {
    expect('env' in nextConfig).toBe(false);
  });

  it('negative control: an absolute base URL fails the check', () => {
    expect(() => checkSameOrigin('http://localhost:8000/api/v1')).toThrow(
      'names an origin',
    );
  });
});
