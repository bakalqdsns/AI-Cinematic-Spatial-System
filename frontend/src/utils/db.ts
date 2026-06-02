// ─────────────────────────────────────────────────────────────────────────────
// IndexedDB persistence layer
// Stores analysis sessions so data survives page refresh.
// ─────────────────────────────────────────────────────────────────────────────
import type { CropParams, ImageSizePreset, ResolutionTier } from '../types';

const DB_NAME = 'aicss-sessions';
const DB_VERSION = 1;
const STORE_NAME = 'sessions';

export interface StoredSession {
  id: string;
  timestamp: number;
  // Cropped image as Blob
  croppedImageBlob: Blob | null;
  cropParams: CropParams | null;
  // Original (pre-crop) image as Blob
  originalImageBlob: Blob | null;
  originalWidth: number;
  originalHeight: number;
  // Analysis result (JSON — not large, safe as string)
  analysisJson: string | null;
  // Billboard assets as base64 strings
  billboardAssetsJson: string | null;
  // Inpaint result as Blob
  inpaintResultBlob: Blob | null;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function makeKey() {
  return `session_${Date.now()}`;
}

export async function saveSession(data: Omit<StoredSession, 'id' | 'timestamp'>): Promise<string> {
  const db = await openDB();
  const id = makeKey();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put({ ...data, id, timestamp: Date.now() });
    tx.oncomplete = () => resolve(id);
    tx.onerror = () => reject(tx.error);
  });
}

export async function updateSession(
  id: string,
  updates: Partial<Omit<StoredSession, 'id' | 'timestamp'>>,
): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const existing = getReq.result;
      if (!existing) { resolve(); return; }
      store.put({ ...existing, ...updates });
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function loadSession(id: string): Promise<StoredSession | null> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).get(id);
    req.onsuccess = () => resolve(req.result ?? null);
    req.onerror = () => reject(req.error);
  });
}

export async function listSessions(): Promise<Array<{ id: string; timestamp: number }>> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = () =>
      resolve(
        (req.result as StoredSession[])
          .map((s) => ({ id: s.id, timestamp: s.timestamp }))
          .sort((a, b) => b.timestamp - a.timestamp),
      );
    req.onerror = () => reject(req.error);
  });
}

export async function deleteSession(id: string): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export function blobToUrl(blob: Blob): string {
  return URL.createObjectURL(blob);
}

export function dataUrlToBlob(dataUrl: string): Blob {
  const [header, data] = dataUrl.split(',');
  const mime = header.match(/:(.*?);/)?.[1] ?? 'image/png';
  const binary = atob(data);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
  return new Blob([arr], { type: mime });
}
