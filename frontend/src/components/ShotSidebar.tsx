import { useScriptStore } from '../store/useScriptStore';
import { useShotWorkflowStore } from '../store/useShotWorkflowStore';

function Mark({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`text-[10px] px-1 rounded ${on ? 'bg-emerald-900/60 text-emerald-300' : 'bg-gray-800 text-gray-500'}`}>
      {label}
    </span>
  );
}

export function ShotSidebar() {
  const shots = useScriptStore((s) => s.shots);
  const selectedShotId = useScriptStore((s) => s.selectedShotId);
  const selectShot = useScriptStore((s) => s.selectShot);
  const progress = useShotWorkflowStore((s) => s.progress);

  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 bg-gray-950 flex flex-col min-h-0">
      <div className="px-3 py-2 border-b border-gray-800 text-xs text-gray-400 uppercase tracking-wider">
        分镜
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {shots.length === 0 && (
          <p className="text-xs text-gray-500 px-1 py-2">解析剧本并生成分镜后，分镜会出现在这里。</p>
        )}
        {shots.map((shot) => {
          const state = progress[shot.id];
          const active = shot.id === selectedShotId;
          const line = shot.actionSummary || shot.visualPrompts.actionPrompt || '无动作';
          return (
            <button
              key={shot.id}
              type="button"
              onClick={() => selectShot(shot.id)}
              className={`w-full text-left rounded-lg px-2 py-2 border transition-colors ${
                active
                  ? 'border-blue-500 bg-blue-950/40'
                  : 'border-transparent hover:bg-gray-900'
              }`}
            >
              <div className="text-sm text-gray-100">镜 {shot.shotNumber}</div>
              <div className="text-[11px] text-gray-400 line-clamp-2 mt-0.5">{line}</div>
              <div className="flex gap-1 mt-1.5">
                <Mark on={!!state?.sceneDone} label="场景" />
                <Mark on={!!state?.actionDone} label="动作" />
                <Mark on={!!state?.renderDone} label="渲染" />
              </div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
