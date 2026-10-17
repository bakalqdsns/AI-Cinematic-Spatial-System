import type {
  CharacterAsset,
  MotionSequence,
  SceneAsset,
  ScriptData,
  ScriptLanguage,
  Shot,
} from '../types/script';
import type { ShotProgress } from '../store/useShotWorkflowStore';
import { useScriptStore } from '../store/useScriptStore';
import { useShotWorkflowStore } from '../store/useShotWorkflowStore';
import { imageSrc } from './projectFiles';

const BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';
const LAST_KEY = 'aicss-last-project';

export interface ProjectRecord {
  projectId: string;
  rawScript: string;
  language: ScriptLanguage;
  normalizedScript: string;
  parsedScript: ScriptData | null;
  shots: Shot[];
  selectedShotId: string | null;
  characterAssets: Record<string, CharacterAsset>;
  sceneAssets: Record<string, SceneAsset>;
  motionSequences: Record<string, MotionSequence>;
  progress: Record<string, ShotProgress>;
  missingFiles?: string[];
}

let applying = false;
let timer: number | null = null;
let started = false;

function slimValue(value: unknown): unknown {
  if (typeof value === 'string') {
    if (value.startsWith('data:')) return undefined;
    if (value.length > 400 && !value.includes('/') && !value.includes('\\')) return undefined;
    return value;
  }
  if (Array.isArray(value)) return value.map(slimValue);
  if (value && typeof value === 'object') {
    const next: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (key === 'layeredImages') continue;
      const slim = slimValue(item);
      if (slim !== undefined) next[key] = slim;
    }
    return next;
  }
  return value;
}

export function buildRecord(): ProjectRecord | null {
  const script = useScriptStore.getState();
  if (!script.projectId) return null;
  const progress = useShotWorkflowStore.getState().progress;
  return slimValue({
    projectId: script.projectId,
    rawScript: script.rawScript,
    language: script.language,
    normalizedScript: script.normalizedScript,
    parsedScript: script.parsedScript,
    shots: script.shots,
    selectedShotId: script.selectedShotId,
    characterAssets: script.characterAssets,
    sceneAssets: script.sceneAssets,
    motionSequences: script.motionSequences,
    progress,
  }) as ProjectRecord;
}

async function putRecord(record: ProjectRecord): Promise<ProjectRecord> {
  const response = await fetch(
    `${BACKEND}/api/aicss/v2/projects/${encodeURIComponent(record.projectId)}/projects.json`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(record),
    },
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '保存剧本记录失败');
  }
  return response.json() as Promise<ProjectRecord>;
}

export function applyRecord(record: ProjectRecord) {
  applying = true;
  useScriptStore.getState().replaceFromRecord(record);
  useShotWorkflowStore.getState().replaceAll(record.projectId, record.progress || {});
  localStorage.setItem(LAST_KEY, record.projectId);
  applying = false;
}

let flushChain: Promise<void> = Promise.resolve();

export function flushRecord() {
  const run = flushChain.then(async () => {
    const record = buildRecord();
    if (!record) return;
    const saved = await putRecord(record);
    localStorage.setItem(LAST_KEY, record.projectId);
    const missing = saved.missingFiles || [];
    const current = useScriptStore.getState().missingFiles;
    if (current.join('|') !== missing.join('|')) {
      applying = true;
      useScriptStore.setState({ missingFiles: missing });
      applying = false;
    }
  });
  flushChain = run.catch((err) => {
    console.warn('[record] 保存失败', err);
  });
  return run;
}

function schedule() {
  if (applying) return;
  if (!useScriptStore.getState().projectId) return;
  if (timer) window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    timer = null;
    void flushRecord();
  }, 400);
}

export function startRecordSync() {
  if (started) return;
  started = true;
  useScriptStore.subscribe(schedule);
  useShotWorkflowStore.subscribe(schedule);
}

export async function loadRecord(projectId: string): Promise<ProjectRecord> {
  const response = await fetch(
    `${BACKEND}/api/aicss/v2/projects/${encodeURIComponent(projectId)}/projects.json`,
  );
  if (!response.ok) throw new Error('没有读到这个剧本的 projects.json');
  return response.json() as Promise<ProjectRecord>;
}

export async function importRecord(record: ProjectRecord): Promise<ProjectRecord> {
  const response = await fetch(`${BACKEND}/api/aicss/v2/projects/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '导入失败');
  }
  return response.json() as Promise<ProjectRecord>;
}

export async function uploadProjectFile(projectId: string, rel: string, file: File): Promise<string> {
  const body = new FormData();
  body.append('rel', rel);
  body.append('file', file);
  const response = await fetch(`${BACKEND}/api/aicss/v2/projects/${encodeURIComponent(projectId)}/files`, {
    method: 'POST',
    body,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '文件没有写入项目');
  }
  const data = await response.json() as { path: string };
  return data.path;
}

export interface IngestedVideo {
  videoPath: string;
  frameCount: number;
  segmentedFrames: { frameIndex: number; path: string; filename: string }[];
  status: 'done' | 'error';
  error?: string | null;
}

export async function ingestActionVideo(
  projectId: string,
  shotId: string,
  characterId: string,
  file: File,
): Promise<IngestedVideo> {
  const body = new FormData();
  body.append('character_id', characterId);
  body.append('file', file);
  const response = await fetch(
    `${BACKEND}/api/aicss/v2/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/action-video`,
    { method: 'POST', body },
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '视频没有处理完');
  }
  return response.json() as Promise<IngestedVideo>;
}

export async function restoreLastProject() {
  const last = localStorage.getItem(LAST_KEY);
  if (!last || useScriptStore.getState().projectId) return;
  const record = await loadRecord(last);
  applyRecord(record);
}

export { imageSrc };
