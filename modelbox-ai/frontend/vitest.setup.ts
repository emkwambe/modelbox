import '@testing-library/jest-dom/vitest';

/**
 * jsdom implements neither ResizeObserver nor matchMedia, and React Flow calls
 * both on mount. Stubbing them here rather than in each canvas test keeps the
 * absence from looking like a component defect when a test fails.
 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (!('ResizeObserver' in globalThis)) {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;
}

if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
