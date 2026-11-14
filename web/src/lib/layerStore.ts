// Where the last answer of each layer is kept in this browser (IndexedDB: answers can be a few megabytes).
// When the browser has no storage (private window, blocked) answers are kept for the visit only.
import { memoryStore, type LiveStore, type Saved } from "@/lib/liveLayer";

const DB = "urbs-layers";
const TABLE = "answers";
/** Basis: about every layer of the catalogue for a couple of areas; older answers are dropped first. */
const MAX_SAVED = 40;

interface Row extends Saved {
  key: string;
}

const done = <T>(req: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

function open(): Promise<IDBDatabase> {
  const req = indexedDB.open(DB, 1);
  req.onupgradeneeded = () => req.result.createObjectStore(TABLE, { keyPath: "key" }).createIndex("at", "at");
  return done(req);
}

function idbStore(): LiveStore {
  let db: Promise<IDBDatabase> | null = null;
  const table = async (mode: IDBTransactionMode) => (await (db ??= open())).transaction(TABLE, mode).objectStore(TABLE);
  return {
    async get(key) {
      const row = (await done((await table("readonly")).get(key))) as Row | undefined;
      return row ? { at: row.at, value: row.value } : null;
    },
    async set(key, saved) {
      const t = await table("readwrite");
      await done(t.put({ key, ...saved } satisfies Row));
      // Oldest first out, so the browser never fills up with layers nobody opens any more.
      let extra = (await done(t.count())) - MAX_SAVED;
      if (extra <= 0) return;
      const cursor = t.index("at").openKeyCursor();
      cursor.onsuccess = () => {
        const c = cursor.result;
        if (!c || extra-- <= 0) return;
        t.delete(c.primaryKey);
        c.continue();
      };
    },
    async clear() {
      await done((await table("readwrite")).clear());
    },
  };
}

/** The saved answers of this browser. Any storage failure falls back to memory: the layer still loads, just not instantly next time. */
export const layerStore: LiveStore = (() => {
  const memory = memoryStore();
  if (typeof indexedDB === "undefined") return memory;
  const disk = idbStore();
  return {
    get: (key) => disk.get(key).catch(() => memory.get(key)),
    set: (key, saved) => disk.set(key, saved).catch(() => memory.set(key, saved)),
    clear: () => Promise.all([disk.clear().catch(() => undefined), memory.clear()]).then(() => undefined),
  };
})();
