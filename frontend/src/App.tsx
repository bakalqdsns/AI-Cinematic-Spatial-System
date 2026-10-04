import { useEffect, useState } from 'react';
import { Film, BookText, Image as ImageIcon, Layers } from 'lucide-react';
import { SettingsPanel } from './components/SettingsPanel';
import { ShotSidebar } from './components/ShotSidebar';
import { ScriptEditor } from './components/ScriptEditor';
import { SplitControls } from './components/SplitControls';
import { SequencePanel } from './components/sequence/SequencePanel';
import { FinishPanel } from './components/FinishPanel';
import { useScriptStore } from './store/useScriptStore';
import { useShotWorkflowStore } from './store/useShotWorkflowStore';

type AppMode = 'script' | 'single' | 'sequence' | 'finish';

const MODES: { id: AppMode; label: string; icon: typeof Film }[] = [
  { id: 'script', label: 'Script', icon: BookText },
  { id: 'single', label: 'Single', icon: ImageIcon },
  { id: 'sequence', label: 'Sequence', icon: Film },
  { id: 'finish', label: '成片', icon: Layers },
];

export default function App() {
  const [appMode, setAppMode] = useState<AppMode>('script');
  const projectId = useScriptStore((s) => s.projectId);
  const hydrate = useShotWorkflowStore((s) => s.hydrate);

  useEffect(() => {
    hydrate(projectId);
  }, [projectId, hydrate]);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-gray-950 text-white">
      <header className="flex items-center gap-3 px-4 py-3 bg-gray-950 border-b border-gray-800">
        <div className="flex items-center gap-2 mr-2">
          <Film size={22} className="text-blue-400" />
          <span className="font-bold text-lg tracking-tight">AICSS</span>
        </div>
        <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1 border border-gray-700">
          {MODES.map((mode) => {
            const Icon = mode.icon;
            const active = appMode === mode.id;
            return (
              <button
                key={mode.id}
                type="button"
                onClick={() => setAppMode(mode.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${
                  active ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
                }`}
              >
                <Icon size={14} />
                {mode.label}
              </button>
            );
          })}
        </div>
        <div className="flex-1" />
        <SettingsPanel />
      </header>
      <div className="flex flex-1 min-h-0">
        <ShotSidebar />
        <main className="flex-1 min-w-0 min-h-0">
          {appMode === 'script' && <ScriptEditor />}
          {appMode === 'single' && <SplitControls />}
          {appMode === 'sequence' && <SequencePanel />}
          {appMode === 'finish' && <FinishPanel />}
        </main>
      </div>
    </div>
  );
}
