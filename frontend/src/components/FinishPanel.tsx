import { useState } from 'react';
import axios from 'axios';
import { useScriptStore } from '../store/useScriptStore';
import { useShotWorkflowStore } from '../store/useShotWorkflowStore';
import { archiveShot, refineRenderVideo, renderPlaybackUrl, renderShot } from '../services/scriptService';

function filenameOf(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || '';
}

export function FinishPanel() {
  const shot = useScriptStore((s) => s.shots.find((item) => item.id === s.selectedShotId) ?? null);
  const projectId = useScriptStore((s) => s.projectId);
  const progress = useShotWorkflowStore((s) => (shot ? s.progress[shot.id] : undefined));
  const patch = useShotWorkflowStore((s) => s.patch);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');

  if (!shot) {
    return <div className="h-full flex items-center justify-center text-gray-500">请在左侧选择一条分镜</div>;
  }

  const ready = !!progress?.sceneDone && !!progress?.actionDone;
  const renderName = progress?.renderPath ? filenameOf(progress.renderPath) : '';
  const refineName = progress?.refinePath ? filenameOf(progress.refinePath) : '';

  const startRender = async () => {
    if (!projectId) return;
    setBusy('正在归档并渲染…');
    setError(null);
    try {
      await archiveShot(projectId, shot.id, shot.sceneId);
      const result = await renderShot(projectId, shot.id);
      if (result.status !== 'succeeded' || !result.outputPath) {
        throw new Error(result.error || '渲染失败');
      }
      patch(shot.id, { renderDone: true, renderPath: result.outputPath });
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (typeof err.response?.data?.detail === 'string' ? err.response.data.detail : err.message)
        : (err instanceof Error ? err.message : String(err));
      setError(message);
    } finally {
      setBusy(null);
    }
  };

  const refine = async () => {
    if (!projectId || !prompt.trim()) return;
    setBusy('正在以渲染结果为参考生成视频…');
    setError(null);
    try {
      const result = await refineRenderVideo(projectId, shot.id, prompt.trim());
      patch(shot.id, { refinePath: result.outputPath });
    } catch (err) {
      const message = axios.isAxiosError(err)
        ? (typeof err.response?.data?.detail === 'string' ? err.response.data.detail : err.message)
        : (err instanceof Error ? err.message : String(err));
      setError(message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 max-w-3xl">
      <p className="text-sm text-gray-400">
        场景 {progress?.sceneDone ? '已完成' : '未完成'} · 动作 {progress?.actionDone ? '已完成' : '未完成'}
      </p>
      <button
        type="button"
        disabled={!ready || !!busy}
        onClick={startRender}
        className="px-4 py-2 rounded bg-blue-600 text-sm disabled:opacity-40"
      >
        开始渲染
      </button>
      {!ready && <p className="text-xs text-gray-500">场景和动作都完成后才能渲染。</p>}
      {busy && <p className="text-sm text-gray-300">{busy}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {projectId && renderName && (
        <div className="space-y-2">
          <div className="text-sm text-gray-200">渲染预览</div>
          <video
            key={renderName}
            src={renderPlaybackUrl(projectId, renderName)}
            controls
            className="w-full max-h-80 bg-black rounded"
          />
        </div>
      )}

      <div className="space-y-2 border-t border-gray-800 pt-4">
        <div className="text-sm text-gray-200">视频生视频</div>
        <p className="text-xs text-gray-500">参考视频固定为上面这条渲染结果。</p>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="写一句生成说明"
          className="w-full h-24 rounded bg-gray-900 border border-gray-700 p-2 text-sm"
        />
        <button
          type="button"
          disabled={!progress?.renderDone || !prompt.trim() || !!busy}
          onClick={refine}
          className="px-4 py-2 rounded bg-emerald-700 text-sm disabled:opacity-40"
        >
          生成
        </button>
        {projectId && refineName && (
          <video
            key={refineName}
            src={renderPlaybackUrl(projectId, refineName)}
            controls
            className="w-full max-h-80 bg-black rounded"
          />
        )}
      </div>
    </div>
  );
}
