import { useEffect, useState } from 'react';
import { Film, BookText, Image as ImageIcon, Layers } from 'lucide-react';
import { SettingsPanel } from './components/SettingsPanel';
import { ShotSidebar } from './components/ShotSidebar';
import { ScriptEditor } from './components/ScriptEditor';
import { SplitControls } from './components/SplitControls';
import { SequencePanel } from './components/sequence/SequencePanel';
import { FinishPanel } from './components/FinishPanel';
import { useScriptStore } from './store/useScriptStore';
import { applyRecord, importRecord, restoreLastProject, startRecordSync } from './services/recordService';
import type { ProjectRecord } from './services/recordService';

type AppMode = 'script' | 'single' | 'sequence' | 'finish';

const MODES: { id: AppMode; label: string; icon: typeof Film }[] = [
  { id: 'script', label: 'Script', icon: BookText },
  { id: 'single', label: 'Single', icon: ImageIcon },
  { id: 'sequence', label: 'Sequence', icon: Film },
  { id: 'finish', label: '成片', icon: Layers },
];

export default function App() {
  const [appMode, setAppMode] = useState<AppMode>('script');
  const [importError, setImportError] = useState<string | null>(null);
  const missingFiles = useScriptStore((s) => s.missingFiles);

  useEffect(() => {
    startRecordSync();
    void restoreLastProject().catch(() => undefined);
  }, []);

  const onRecordFile = async (file: File) => {
    setImportError(null);
    try {
      const parsed = JSON.parse(await file.text()) as ProjectRecord;
      const stored = await importRecord(parsed);
      applyRecord(stored);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : '这份 projects.json 没有读进来');
    }
  };

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
        <label
          className="ml-2 px-3 py-1.5 text-xs rounded border border-dashed border-gray-600 text-gray-300 cursor-pointer"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            const file = event.dataTransfer.files?.[0];
            if (file) void onRecordFile(file);
          }}
        >
          拖入 projects.json
          <input
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onRecordFile(file);
              event.target.value = '';
            }}
          />
        </label>
        <div className="flex-1" />
        <SettingsPanel />
      </header>
      {importError && <div className="px-4 py-2 text-xs text-red-300 bg-red-950">{importError}</div>}
      {missingFiles.length > 0 && (
        <div className="px-4 py-2 text-xs text-amber-200 bg-amber-950">
          这些路径在剧本目录里对不上：{missingFiles.join('、')}
        </div>
      )}
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
