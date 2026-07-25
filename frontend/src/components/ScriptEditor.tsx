// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Editor — Top-level UI for the script splitting pipeline.
//
// Hosts four tabs:
//   1. Script     — raw script input + parsed breakdown (characters / scenes
//                   / story paragraphs)
//   2. Storyboard — per-shot cards with selected shot detail panel
//   3. Characters — character list with 3-view + variation generation
//   4. Motion     — shot × character motion video generation
// ─────────────────────────────────────────────────────────────────────────────
import React, { useState } from 'react';
import { useScriptStore } from '../store/useScriptStore';
import type {
  ScriptLanguage, Character, CharacterAsset, Shot,
  ScriptData,
} from '../types/script';

const LANGUAGES: { value: ScriptLanguage; label: string }[] = [
  { value: 'chinese', label: '中文' },
  { value: 'english', label: 'English' },
  { value: 'japanese', label: '日本語' },
];

type TabId = 'script' | 'storyboard' | 'characters' | 'motion';

export const ScriptEditor: React.FC = () => {
  const {
    rawScript, setRawScript,
    language, setLanguage,
    parsedScript,
    normalizedScript,
    isParsing,
    isExtractingCharacters,
    extractedCharacters,
    error,
    parseScript,
    extractCharacters,
    generateShots,
    isGeneratingShots,
    activeTab, setActiveTab,
    selectedShotId, selectShot,
    selectedCharacterId, selectCharacter,
    shots,
    characterAssets,
    generateCharacterThreeView,
    isGeneratingCharacter,
  } = useScriptStore();

  // Project context is currently sourced from the future persisted-session
  // flow. Keeping it null here avoids coupling the editor to backend IDs that
  // don't exist yet — the store accepts an optional projectId argument.
  const [projectId] = useState<string | null>(null);

  const handleParse = async () => {
    console.log('[ScriptEditor] handleParse called, rawScript length:', rawScript.length);
    if (!rawScript.trim()) {
      console.log('[ScriptEditor] rawScript is empty, not calling API');
      return;
    }
    try {
      await parseScript(projectId || undefined);
      console.log('[ScriptEditor] parseScript completed');
    } catch (e) {
      console.error('[ScriptEditor] parseScript error:', e);
    }
  };

  const handleGenerateShots = async () => {
    await generateShots(projectId || undefined);
    setActiveTab('storyboard');
  };

  const tabs: { id: TabId; label: string }[] = [
    { id: 'script', label: '剧本数据' },
    { id: 'storyboard', label: '分镜预览' },
    { id: 'characters', label: '角色资产' },
    { id: 'motion', label: '动作序列' },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-900 text-gray-100">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-700 bg-gray-950">
        <select
          className="px-2 py-1 bg-gray-800 border border-gray-700 text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
          value={language}
          onChange={e => setLanguage(e.target.value as ScriptLanguage)}
        >
          {LANGUAGES.map(l => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </select>

        <button
          onClick={handleParse}
          disabled={isParsing || !rawScript.trim()}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          {isParsing ? '解析中...' : '解析剧本'}
        </button>

        <button
          onClick={handleGenerateShots}
          disabled={isGeneratingShots || !parsedScript}
          className="px-4 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          {isGeneratingShots ? '生成分镜中...' : '生成分镜表'}
        </button>

        {error && (
          <span className="text-red-400 text-sm">{error}</span>
        )}

        <div className="ml-auto text-sm text-gray-400">
          {parsedScript && (
            <span>
              {parsedScript.characters.length} 角色 | {parsedScript.scenes.length} 场景 | {shots.length} 分镜
            </span>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-gray-700 bg-gray-900">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-400 font-medium'
                : 'border-transparent text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            {tab.label}
            {tab.id === 'storyboard' && shots.length > 0 && (
              <span className="ml-1 text-xs bg-blue-900/50 text-blue-300 px-1.5 rounded">
                {shots.length}
              </span>
            )}
            {tab.id === 'characters' && parsedScript && (
              <span className="ml-1 text-xs bg-emerald-900/50 text-emerald-300 px-1.5 rounded">
                {parsedScript.characters.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'script' && (
          <ScriptTab
            rawScript={rawScript}
            onRawChange={setRawScript}
            parsedScript={parsedScript}
            extractedCharacters={extractedCharacters}
            isExtractingCharacters={isExtractingCharacters}
            onExtractCharacters={() => extractCharacters(projectId || undefined)}
            normalizedScript={normalizedScript}
            language={language}
          />
        )}
        {activeTab === 'storyboard' && (
          <StoryboardTab
            shots={shots}
            parsedScript={parsedScript}
            selectedShotId={selectedShotId}
            onSelectShot={selectShot}
          />
        )}
        {activeTab === 'characters' && (
          <CharactersTab
            characters={parsedScript?.characters || []}
            characterAssets={characterAssets}
            onGenerateThreeView={generateCharacterThreeView}
            isGenerating={isGeneratingCharacter}
            selectedCharId={selectedCharacterId}
            onSelectChar={selectCharacter}
          />
        )}
        {activeTab === 'motion' && (
          <MotionTab shots={shots} parsedScript={parsedScript} />
        )}
      </div>
    </div>
  );
};

// ==============================
// Tab: Script — raw input + parsed breakdown
// ==============================

interface ScriptTabProps {
  rawScript: string;
  onRawChange: (text: string) => void;
  parsedScript: ScriptData | null;
  extractedCharacters: Character[];
  isExtractingCharacters: boolean;
  onExtractCharacters: () => void;
  normalizedScript: string;
  language: ScriptLanguage;
}

const ScriptTab: React.FC<ScriptTabProps> = ({
  rawScript, onRawChange, parsedScript,
  extractedCharacters, isExtractingCharacters, onExtractCharacters,
  normalizedScript, language,
}) => {
  const [showNormalized, setShowNormalized] = useState(false);

  return (
    <div className="flex h-full">
      {/* Script input */}
      <div className="flex-1 p-4 border-r border-gray-700">
        <h3 className="text-sm font-medium text-gray-200 mb-2">原始剧本</h3>
        <textarea
          className="w-full h-full min-h-[400px] p-3 bg-gray-950 border border-gray-700 text-gray-100 placeholder:text-gray-500 rounded-lg font-mono text-sm resize-none focus:outline-none focus:ring-1 focus:ring-cyan-400"
          placeholder={
            language === 'chinese'
              ? '在此输入或粘贴剧本文本...\n\n示例：\n第一幕 咖啡馆\n\n李明走进咖啡馆，环顾四周。\n\n李明：他已经迟到了半小时了。\n\n张华推门而入。'
              : language === 'english'
              ? 'Enter or paste your script here...\n\nExample:\nINT. COFFEE SHOP - DAY\n\nLi Ming walks into the coffee shop, looking around nervously.\n\nLI MING: He\'s already 30 minutes late.'
              : 'ここに脚本を入力または貼り付けてください...'
          }
          value={rawScript}
          onChange={e => onRawChange(e.target.value)}
        />
      </div>

      {/* Parsed results */}
      {parsedScript && (
        <div className="flex-1 p-4 overflow-auto">
          <div className="mb-4">
            <h2 className="text-lg font-bold text-gray-100">{parsedScript.title || '无标题'}</h2>
            <p className="text-sm text-gray-400">
              {parsedScript.genre} — {parsedScript.logline}
            </p>
          </div>

          {/* Normalized script toggle — useful for debugging the LLM normalization pass */}
          {normalizedScript && (
            <div className="mb-4">
              <button
                onClick={() => setShowNormalized(!showNormalized)}
                className="text-sm text-cyan-400 hover:text-cyan-300 underline"
              >
                {showNormalized ? '隐藏标准化剧本' : '显示标准化剧本'}
              </button>
              {showNormalized && (
                <pre className="mt-2 p-2 bg-gray-950 border border-gray-700 text-gray-300 rounded text-xs whitespace-pre-wrap max-h-48 overflow-auto">
                  {normalizedScript}
                </pre>
              )}
            </div>
          )}

          {/* Characters — character-first pipeline: prefer pre-extracted
              characters (shown as soon as the /characters/extract call
              returns, even while /parse is still in flight). Fall back to
              parsedScript.characters once parse completes. */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-200">
                角色 ({(extractedCharacters.length || parsedScript.characters.length)})
                {isExtractingCharacters && (
                  <span className="ml-2 text-xs text-cyan-400 font-normal">识别中…</span>
                )}
              </h3>
              <button
                type="button"
                onClick={onExtractCharacters}
                disabled={isExtractingCharacters || !rawScript.trim()}
                className="text-xs px-2 py-1 border border-gray-700 bg-gray-800 text-gray-300 rounded hover:bg-gray-700 hover:border-gray-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                title="重新识别角色（仅触发 Pass 1.5）"
              >
                {isExtractingCharacters ? '识别中…' : '重新识别'}
              </button>
            </div>
            <div className="space-y-2">
              {(extractedCharacters.length ? extractedCharacters : parsedScript.characters).map(char => (
                <div key={char.id} className="p-2 bg-gray-800/60 rounded border border-gray-700">
                  <div className="font-medium text-sm text-gray-100">{char.name}</div>
                  <div className="text-xs text-gray-400">
                    {char.gender} | {char.age} | {char.personality}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Scenes */}
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-gray-200 mb-2">
              场景 ({parsedScript.scenes.length})
            </h3>
            <div className="space-y-2">
              {parsedScript.scenes.map(scene => (
                <div key={scene.id} className="p-2 bg-cyan-950/40 rounded border border-cyan-800/60">
                  <div className="font-medium text-sm text-gray-100">{scene.location}</div>
                  <div className="text-xs text-gray-400">
                    {scene.time} | {scene.atmosphere}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Story paragraphs */}
          <div>
            <h3 className="text-sm font-semibold text-gray-200 mb-2">
              故事段落 ({parsedScript.storyParagraphs.length})
            </h3>
            <div className="space-y-2">
              {parsedScript.storyParagraphs.map(para => {
                const scene = parsedScript.scenes.find(s => s.id === para.sceneRefId);
                return (
                  <div key={para.id} className="p-2 bg-amber-950/30 rounded border border-amber-800/60">
                    <div className="text-xs text-cyan-400 font-medium mb-1">
                      [{scene?.location || para.sceneRefId}]
                    </div>
                    <div className="text-sm text-gray-300">{para.text.slice(0, 200)}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ==============================
// Tab: Storyboard — per-shot cards + detail panel
// ==============================

interface StoryboardTabProps {
  shots: Shot[];
  parsedScript: ScriptData | null;
  selectedShotId: string | null;
  onSelectShot: (id: string | null) => void;
}

const StoryboardTab: React.FC<StoryboardTabProps> = ({
  shots, parsedScript, selectedShotId, onSelectShot,
}) => {
  if (shots.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <div className="text-4xl mb-2">🎬</div>
          <p>解析剧本后生成分镜表</p>
        </div>
      </div>
    );
  }

  const selectedShot = shots.find(s => s.id === selectedShotId);

  return (
    <div className="flex h-full">
      {/* Shot grid */}
      <div className="flex-1 p-4 overflow-auto">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {shots.map(shot => {
            const scene = parsedScript?.scenes.find(s => s.id === shot.sceneId);
            const chars = (parsedScript?.characters || []).filter(c => shot.characters.includes(c.id));

            return (
              <div
                key={shot.id}
                onClick={() => onSelectShot(shot.id === selectedShotId ? null : shot.id)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  shot.id === selectedShotId
                    ? 'border-cyan-400 bg-cyan-950/40 shadow-[0_0_0_1px_rgba(34,211,238,0.5)]'
                    : 'border-gray-700 bg-gray-900 hover:border-gray-500 hover:shadow'
                }`}
              >
                {/* Shot number & badges */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-bold text-cyan-300">
                    镜 {shot.shotNumber}
                  </span>
                  <div className="flex gap-1">
                    <span className="text-[10px] px-1.5 py-0.5 bg-gray-800 text-gray-300 rounded">
                      {shot.shotSize}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded">
                      {shot.cameraMovement}
                    </span>
                  </div>
                </div>

                {/* Scene & action */}
                <div className="text-xs text-gray-400 mb-1">
                  {scene?.location || shot.sceneId}
                </div>
                <div className="text-sm text-gray-200 mb-2 line-clamp-2">
                  {shot.actionSummary || shot.visualPrompts.actionPrompt}
                </div>

                {/* Characters */}
                <div className="flex flex-wrap gap-1 mb-2">
                  {chars.map(c => (
                    <span key={c.id} className="text-[10px] px-1.5 py-0.5 bg-emerald-900/50 text-emerald-300 rounded">
                      {c.name}
                    </span>
                  ))}
                </div>

                {/* Duration */}
                <div className="text-xs text-gray-400">
                  {shot.durationSeconds}s
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Shot detail panel */}
      {selectedShot && (
        <div className="w-96 border-l border-gray-700 bg-gray-900 p-4 overflow-auto">
          <h3 className="text-lg font-bold mb-3 text-gray-100">
            镜 {selectedShot.shotNumber}
          </h3>

          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-400">景别</label>
              <div className="text-sm font-medium text-gray-100">{selectedShot.shotSize}</div>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">运镜</label>
              <div className="text-sm text-gray-200">{selectedShot.cameraMovement}</div>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">场景提示词</label>
              <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs whitespace-pre-wrap">
                {selectedShot.visualPrompts.scenePrompt || selectedShot.keyframeStartPrompt || '-'}
              </pre>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">动作提示词</label>
              <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs whitespace-pre-wrap">
                {selectedShot.visualPrompts.actionPrompt || '-'}
              </pre>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">相机提示词</label>
              <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs">
                {selectedShot.visualPrompts.cameraPrompt || '-'}
              </pre>
            </div>

            {selectedShot.dialogue && (
              <div>
                <label className="text-xs font-medium text-gray-400">对白</label>
                <div className="mt-1 p-2 bg-amber-950/30 border border-amber-800/60 text-gray-200 rounded text-sm italic">
                  {selectedShot.dialogue}
                </div>
              </div>
            )}

            <div>
              <label className="text-xs font-medium text-gray-400">时长</label>
              <div className="text-sm text-gray-200">{selectedShot.durationSeconds}s</div>
            </div>

            {(selectedShot.keyframeStartPrompt || selectedShot.keyframeEndPrompt) && (
              <>
                <div>
                  <label className="text-xs font-medium text-gray-400">起始帧提示词</label>
                  <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs">
                    {selectedShot.keyframeStartPrompt || '-'}
                  </pre>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-400">结束帧提示词</label>
                  <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs">
                    {selectedShot.keyframeEndPrompt || '-'}
                  </pre>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ==============================
// Tab: Characters — list + 3-view + variations
// ==============================

interface CharactersTabProps {
  characters: Character[];
  characterAssets: Record<string, CharacterAsset>;
  onGenerateThreeView: (charId: string, projectId?: string) => Promise<void>;
  isGenerating: Record<string, boolean>;
  selectedCharId: string | null;
  onSelectChar: (id: string | null) => void;
}

const CharactersTab: React.FC<CharactersTabProps> = ({
  characters, characterAssets, onGenerateThreeView, isGenerating, selectedCharId, onSelectChar,
}) => {
  if (characters.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <p>解析剧本后查看角色</p>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Character list */}
      <div className="w-64 border-r border-gray-700 p-4 overflow-auto">
        <h3 className="text-sm font-semibold text-gray-200 mb-3">角色列表</h3>
        <div className="space-y-2">
          {characters.map(char => {
            const asset = characterAssets[char.id];
            return (
              <div
                key={char.id}
                onClick={() => onSelectChar(char.id === selectedCharId ? null : char.id)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  char.id === selectedCharId
                    ? 'border-emerald-400 bg-emerald-950/40'
                    : 'border-gray-700 bg-gray-900 hover:border-gray-500'
                }`}
              >
                <div className="font-medium text-sm text-gray-100">{char.name}</div>
                <div className="text-xs text-gray-400">{char.gender} | {char.age}</div>
                {asset?.referenceImage && (
                  <div className="mt-2">
                    <img
                      src={`data:image/png;base64,${asset.referenceImage}`}
                      alt={char.name}
                      className="w-full h-24 object-cover rounded"
                    />
                  </div>
                )}
                {asset?.threeViewImages?.front && (
                  <div className="mt-1 text-xs text-emerald-400">✓ 三视图已生成</div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Character detail */}
      {selectedCharId && (() => {
        const char = characters.find(c => c.id === selectedCharId);
        if (!char) return null;
        const asset = characterAssets[char.id];

        return (
          <div className="flex-1 p-4 overflow-auto">
            <div className="mb-4">
              <h2 className="text-xl font-bold text-gray-100">{char.name}</h2>
              <p className="text-sm text-gray-400">{char.personality}</p>
            </div>

            {/* Generate button */}
            <button
              onClick={() => onGenerateThreeView(char.id)}
              disabled={isGenerating[char.id]}
              className="mb-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {isGenerating[char.id] ? '生成中...' : '生成三视图'}
            </button>

            {/* Three view images */}
            {asset?.threeViewImages && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-200 mb-2">三视图</h3>
                <div className="grid grid-cols-3 gap-2">
                  {(['front', 'side', 'back'] as const).map(view => {
                    const img = asset.threeViewImages[view];
                    return (
                      <div key={view} className="text-center">
                        <div className="text-xs text-gray-400 mb-1 capitalize">{view}</div>
                        {img ? (
                          <img
                            src={`data:image/png;base64,${img}`}
                            alt={view}
                            className="w-full aspect-square object-cover rounded border border-gray-700"
                          />
                        ) : (
                          <div className="w-full aspect-square bg-gray-800 border border-gray-700 rounded flex items-center justify-center text-gray-500 text-xs">
                            未生成
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Visual prompt */}
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-gray-200 mb-1">视觉提示词</h3>
              <textarea
                className="w-full p-2 bg-gray-950 border border-gray-700 text-gray-100 placeholder:text-gray-500 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
                rows={4}
                value={char.visualPrompt || asset?.visualPrompt || ''}
                placeholder="自动生成或手动编辑..."
              />
            </div>

            {/* Variations */}
            {asset?.variations && asset.variations.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-200 mb-2">服装变体</h3>
                <div className="grid grid-cols-3 gap-2">
                  {asset.variations.map(v => (
                    <div key={v.id} className="bg-gray-800/60 border border-gray-700 rounded-lg p-2">
                      <div className="text-xs text-gray-400 mb-1">{v.name}</div>
                      {v.image && (
                        <img
                          src={`data:image/png;base64,${v.image}`}
                          alt={v.name}
                          className="w-full aspect-square object-cover rounded"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
};

// ==============================
// Tab: Motion — per (shot × character) motion generation rows
// ==============================

interface MotionTabProps {
  shots: Shot[];
  parsedScript: ScriptData | null;
}

const MotionTab: React.FC<MotionTabProps> = ({ shots, parsedScript }) => {
  const { motionSequences, generateMotion, isGeneratingMotion } = useScriptStore();

  if (shots.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <p>生成分镜表后生成动作序列</p>
      </div>
    );
  }

  const characters = parsedScript?.characters || [];

  return (
    <div className="p-4">
      <h3 className="text-sm font-semibold text-gray-200 mb-4">动作序列生成</h3>
      <div className="space-y-3">
        {shots.map(shot => {
          const chars = characters.filter(c => shot.characters.includes(c.id));
          return chars.map(char => {
            const key = `${shot.id}_${char.id}`;
            const motion = motionSequences[key];

            return (
              <div key={key} className="p-3 border border-gray-700 rounded-lg bg-gray-900">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="font-medium text-sm text-gray-100">镜 {shot.shotNumber}</span>
                    <span className="mx-2 text-gray-600">×</span>
                    <span className="text-sm text-emerald-300">{char.name}</span>
                  </div>
                  {motion && (
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      motion.status === 'done' ? 'bg-emerald-900/50 text-emerald-300' :
                      motion.status === 'error' ? 'bg-red-900/50 text-red-300' :
                      'bg-amber-900/50 text-amber-300'
                    }`}>
                      {motion.status}
                    </span>
                  )}
                </div>

                <div className="text-xs text-gray-400 mb-2 line-clamp-1">
                  {shot.visualPrompts.actionPrompt}
                </div>

                <button
                  onClick={() => generateMotion(shot.id, char.id)}
                  disabled={isGeneratingMotion[key]}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                >
                  {isGeneratingMotion[key] ? '生成中...' : '生成动作视频'}
                </button>

                {motion && motion.frameCount > 0 && (
                  <div className="mt-2 text-xs text-gray-400">
                    {motion.frameCount} 帧已提取
                    {motion.segmentedDir && ' | 已分割'}
                  </div>
                )}
                {motion?.error && (
                  <div className="mt-2 text-xs text-red-400">
                    错误: {motion.error}
                  </div>
                )}
              </div>
            );
          });
        })}
      </div>
    </div>
  );
};