import { create } from 'zustand';

export interface ShotProgress {
  sceneDone: boolean;
  actionDone: boolean;
  renderDone: boolean;
  renderPath?: string;
  refinePath?: string;
}

interface ShotWorkflowState {
  projectId: string | null;
  progress: Record<string, ShotProgress>;
  hydrate: (projectId: string | null) => void;
  patch: (shotId: string, partial: Partial<ShotProgress>) => void;
}

const EMPTY: ShotProgress = {
  sceneDone: false,
  actionDone: false,
  renderDone: false,
};

function storageKey(projectId: string) {
  return `aicss-shot-workflow:${projectId}`;
}

export const useShotWorkflowStore = create<ShotWorkflowState>((set, get) => ({
  projectId: null,
  progress: {},

  hydrate: (projectId) => {
    if (!projectId) {
      set({ projectId: null, progress: {} });
      return;
    }
    try {
      const raw = localStorage.getItem(storageKey(projectId));
      const progress = raw ? (JSON.parse(raw) as Record<string, ShotProgress>) : {};
      set({ projectId, progress });
    } catch {
      set({ projectId, progress: {} });
    }
  },

  patch: (shotId, partial) => {
    const { projectId, progress } = get();
    const next: ShotProgress = { ...EMPTY, ...progress[shotId], ...partial };
    const progressNext = { ...progress, [shotId]: next };
    set({ progress: progressNext });
    if (projectId) {
      localStorage.setItem(storageKey(projectId), JSON.stringify(progressNext));
    }
  },
}));
