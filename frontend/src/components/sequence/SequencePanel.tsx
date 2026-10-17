import { useEffect, useState } from 'react';
import type { Character } from '../../types/script';
import { useScriptStore } from '../../store/useScriptStore';
import { useShotWorkflowStore } from '../../store/useShotWorkflowStore';
import { imageSrc } from '../../services/projectFiles';
import { ingestActionVideo, flushRecord } from '../../services/recordService';
import { CopyPrompt, DropSlot } from '../ManualFill';
import { checkActionPrompt, PromptIssueList } from '../../services/promptCheck';

const EMPTY_CHARACTERS: Character[] = [];

export function SequencePanel() {
  const shot = useScriptStore((s) => s.shots.find((item) => item.id === s.selectedShotId) ?? null);
  const characters = useScriptStore((s) => s.parsedScript?.characters) ?? EMPTY_CHARACTERS;
  const motions = useScriptStore((s) => s.motionSequences);
  const projectId = useScriptStore((s) => s.projectId);
  const setMotion = useScriptStore((s) => s.setMotion);
  const patch = useShotWorkflowStore((s) => s.patch);
  const [frameIndex, setFrameIndex] = useState(0);
  const [activeChar, setActiveChar] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const onVideo = async (characterId: string, characterName: string, file: File) => {
    if (!projectId) {
      setError('先解析剧本，视频才会写入这个剧本的目录');
      return;
    }
    setBusyId(characterId);
    setError(null);
    setActiveChar(characterId);
    setFrameIndex(0);
    try {
      const result = await ingestActionVideo(projectId, shot.id, characterId, file);
      setMotion({
        shotId: shot.id,
        characterId,
        characterName,
        actionDescription: prompt,
        videoPath: result.videoPath,
        frameCount: result.frameCount,
        segmentedFrames: result.segmentedFrames,
        status: result.status,
        error: result.error || undefined,
      });
      if (result.error) setError(result.error);
      await flushRecord();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-gray-300 whitespace-pre-wrap">{prompt}</p>
        <CopyPrompt text={prompt} />
      </div>
      <PromptIssueList issues={checkActionPrompt(prompt)} />
      {cast.length === 0 && <p className="text-sm text-gray-500">这条分镜没有角色。</p>}
      <div className="space-y-3">
        {cast.map((character) => {
          const key = `${shot.id}_${character.id}`;
          const row = motions[key];
          return (
            <div key={character.id} className="border border-gray-800 rounded p-3 space-y-2">
              <div className="flex items-center gap-3">
                <button type="button" className="text-sm text-gray-100" onClick={() => { setActiveChar(character.id); setFrameIndex(0); }}>
                  {character.name}
                </button>
                <span className="text-xs text-gray-500">{row?.status ?? '未导入'}{row ? ` · ${row.frameCount} 帧` : ''}</span>
              </div>
              <DropSlot
                label="拖入这个人物的动作视频，只做抽帧和分割"
                accept="video/*"
                busy={busyId === character.id}
                onFile={(file) => { void onVideo(character.id, character.name, file); }}
              />
              {row?.error && <p className="text-xs text-red-400">{row.error}</p>}
            </div>
          );
        })}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {frame?.path && (
        <div className="space-y-2">
          <img src={imageSrc(projectId, frame.path)} alt="动作帧" className="max-h-80 bg-black rounded" />
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
