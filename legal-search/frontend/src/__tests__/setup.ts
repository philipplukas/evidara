import "@testing-library/jest-dom/vitest";

// Node >= 24 ships an experimental built-in `localStorage` global that resolves
// to `undefined` unless the process is started with `--localstorage-file`.
// Under Vitest's jsdom environment that global shadows jsdom's own Storage, so
// `window.localStorage` reads back `undefined` and any test touching it dies
// with "Cannot read properties of undefined (reading 'clear')". CI pins Node 22
// (`.nvmrc`) and never hits this, but workstations on newer Node do — leaving
// `npm run check` red for reasons unrelated to the change under test. Install a
// deterministic in-memory Storage so the gate is honest on any Node version.
// See #596. Components read storage via both `window.localStorage` and bare
// `localStorage`, so the SAME instance must back both.
function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.has(key) ? (store.get(key) as string) : null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
  };
}

const memoryStorage = createMemoryStorage();
for (const target of [window, globalThis]) {
  Object.defineProperty(target, "localStorage", {
    configurable: true,
    writable: true,
    value: memoryStorage,
  });
}

// Mock window.matchMedia for components that use it (e.g. ThemeToggle)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
