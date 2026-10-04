import { useEffect, useState } from 'react';
import type { Character } from '../../types/script';
import { useScriptStore } from '../../store/useScriptStore';
import { useShotWorkflowStore } from '../../store/useShotWorkflowStore';
import { mediaUrl } from '../../services/scriptService';

const EMPTY_CHARACTERS: Character[] = [];

export function SequencePanel() {
  const shot = useScriptStore((s) => s.shots.find((item) => item.id === s.selectedShotId) ?? null);
  const characters = useScriptStore((s) => s.parsedScript?.characters) ?? EMPTY_CHARACTERS;
  const motions = useScriptStore((s) => s.motionSequences);
  const generating = useScriptStore((s) => s.isGeneratingMotion);
  const generateMotion = useScriptStore((s) => s.generateMotion);
  const projectId = useScriptStore((s) => s.projectId);
  const patch = useShotWorkflowStore((s) => s.patch);
  const [frameIndex, setFrameIndex] = useState(0);
  const [activeChar, setActiveChar] = useState<string | null>(null);

  const cast = shot
    ? characters.filter((character) => shot.characters.includes(character.id))
    : [];
  const prompt = shot?.visualPrompts.actionPrompt?.trim() ?? '';

  const shotId = shot?.id;
  const castKey = shot ? shot.characters.join(',') : '';
  useEffect(() => {
    if (!shotId) return;
    const ids = castKey ? castKey.split(',') : [];
    if (ids.length === 0) return;
    const done = ids.every((id) => {
      const motion = useScriptStore.getState().motionSequences[`${shotId}_${id}`];
      return motion?.status === 'done' && motion.frameCount > 0;
    });
    const current = useShotWorkflowStore.getState().progress[shotId]?.actionDone;
    if (current === done) return;
    patch(shotId, { actionDone: done });
  }, [shotId, castKey, motions, patch]);

  if (!shot) {
    return <div className="h-full flex items-center justify-center text-gray-500">请在左侧选择一条分镜</div>;
  }
  if (!prompt) {
    return <div className="h-full flex items-center justify-center text-gray-400">这条分镜还没有动作提示。</div>;
  }

  const currentId = activeChar ?? cast[0]?.id ?? null;
  const motion = currentId ? motions[`${shot.id}_${currentId}`] : undefined;
  const frames = motion?.segmentedFrames ?? [];
  const frame = frames[Math.min(frameIndex, Math.max(frames.length - 1, 0))];

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <p className="text-sm text-gray-300">{prompt}</p>
      {cast.length === 0 && <p className="text-sm text-gray-500">这条分镜没有角色。</p>}
      <div className="space-y-2">
        {cast.map((character) => {
          const key = `${shot.id}_${character.id}`;
          const row = motions[key];
          return (
            <div key={character.id} className="flex items-center gap-3 border border-gray-800 rounded px-3 py-2">
              <button type="button" className="text-sm text-gray-100" onClick={() => { setActiveChar(character.id); setFrameIndex(0); }}>
                {character.name}
              </button>
              <span className="text-xs text-gray-500">{row?.status ?? '未生成'}{row ? ` · ${row.frameCount} 帧` : ''}</span>
              <button
                type="button"
                disabled={!!generating[key]}
                onClick={() => generateMotion(shot.id, character.id, projectId || undefined)}
                className="ml-auto px-3 py-1 text-xs rounded bg-blue-600 disabled:opacity-50"
              >
                {generating[key] ? '生成中…' : '生成动作视频'}
              </button>
              {row?.error && <span className="text-xs text-red-400">{row.error}</span>}
            </div>
          );
        })}
      </div>
      {frame?.path && (
        <div className="space-y-2">
          <img src={mediaUrl(frame.path)} alt="动作帧" className="max-h-80 bg-black rounded" />
          <input
            type="range"
            min={0}
            max={Math.max(frames.length - 1, 0)}
            value={Math.min(frameIndex, Math.max(frames.length - 1, 0))}
            onChange={(e) => setFrameIndex(Number(e.target.value))}
          />
          <div className="text-xs text-gray-500">{frameIndex + 1} / {frames.length}</div>
        </div>
      )}
    </div>
  );
}
