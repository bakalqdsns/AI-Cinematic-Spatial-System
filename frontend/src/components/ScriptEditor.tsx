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
import React, { useMemo, useState } from 'react';
import { useScriptStore } from '../store/useScriptStore';
import type {
  ScriptLanguage, Character, CharacterAsset, Shot,
  ScriptData, SceneAsset, Scene,
} from '../types/script';

const LANGUAGES: { value: ScriptLanguage; label: string }[] = [
  { value: 'chinese', label: '中文' },
  { value: 'english', label: 'English' },
  { value: 'japanese', label: '日本語' },
];

type TabId = 'script' | 'storyboard' | 'characters' | 'scenes' | 'motion';

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
    updateShot,
    characterAssets,
    generateCharacterThreeView,
    generateCharacterVariation,
    isGeneratingCharacter,
    sceneAssets,
    isGeneratingSceneAsset,
    updateCharacterVisualPrompt,
    updateSceneVisualPrompt,
    resolveCharacterVisualPrompts,
    resolveSceneVisualPrompts,
    selectedSceneId, selectScene,
    generateSceneAsset,
    projectId,
    isResolvingPrompts,
  } = useScriptStore();

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
    { id: 'scenes', label: '场景资产' },
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
            sceneAssets={sceneAssets}
            isGeneratingSceneAsset={isGeneratingSceneAsset}
          />
        )}
        {activeTab === 'storyboard' && (
          <StoryboardTab
            shots={shots}
            parsedScript={parsedScript}
            selectedShotId={selectedShotId}
            onSelectShot={selectShot}
            onUpdateShot={updateShot}
            sceneAssets={sceneAssets}
          />
        )}
        {activeTab === 'characters' && (
          <CharactersTab
            characters={parsedScript?.characters || []}
            characterAssets={characterAssets}
            onGenerateThreeView={generateCharacterThreeView}
            onGenerateVariation={generateCharacterVariation}
            isGenerating={isGeneratingCharacter}
            selectedCharId={selectedCharacterId}
            onSelectChar={selectCharacter}
            onUpdatePrompt={updateCharacterVisualPrompt}
            onResolvePrompt={resolveCharacterVisualPrompts}
            isResolvingPrompts={!!isResolvingPrompts}
          />
        )}
        {activeTab === 'motion' && (
          <MotionTab shots={shots} parsedScript={parsedScript} />
        )}
        {activeTab === 'scenes' && (
          <ScenesTab
            parsedScript={parsedScript}
            sceneAssets={sceneAssets}
            isGeneratingSceneAsset={isGeneratingSceneAsset}
            selectedSceneId={selectedSceneId}
            onSelectScene={selectScene}
            onGenerateSceneAsset={generateSceneAsset}
            onUpdatePrompt={updateSceneVisualPrompt}
            onResolvePrompt={resolveSceneVisualPrompts}
          />
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
  sceneAssets: Record<string, SceneAsset>;
  isGeneratingSceneAsset: Record<string, boolean>;
}

const ScriptTab: React.FC<ScriptTabProps> = ({
  rawScript, onRawChange, parsedScript,
  extractedCharacters, isExtractingCharacters, onExtractCharacters,
  normalizedScript, language,
  sceneAssets, isGeneratingSceneAsset,
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
              {parsedScript.scenes.map(scene => {
                const asset = sceneAssets[scene.id];
                const generating = !!isGeneratingSceneAsset[scene.id];
                const thumbB64 = asset?.keyframeImages?.wide;
                const shotCount = parsedScript.storyParagraphs.filter(
                  p => p.sceneRefId === scene.id && p.containsAction
                ).length;
                return (
                  <div
                    key={scene.id}
                    className="p-2 bg-cyan-950/40 rounded border border-cyan-800/60 flex gap-3"
                  >
                    {/* Wide thumbnail or status badge */}
                    <div className="w-16 h-16 shrink-0 rounded overflow-hidden bg-cyan-900/40 border border-cyan-700/50 flex items-center justify-center text-xs text-gray-300">
                      {thumbB64 ? (
                        <img
                          src={`data:image/png;base64,${thumbB64}`}
                          alt={scene.location}
                          className="w-full h-full object-cover"
                        />
                      ) : generating ? (
                        <span className="animate-pulse text-cyan-200">生成中…</span>
                      ) : (
                        <span className="text-gray-500">—</span>
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-gray-100 truncate">
                        {scene.location}
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {scene.time} | {scene.atmosphere || '未指定氛围'}
                      </div>
                      <div className="text-[10px] text-gray-500 mt-1 flex items-center gap-2">
                        <span>分镜 {shotCount || scene.estimatedShots || 0}</span>
                        {asset && (
                          <span className="text-emerald-400">
                            ✓ {Object.keys(asset.keyframeImages || {}).filter(k => asset.keyframeImages?.[k]).length}/3 视图
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
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
  onUpdateShot: (shotId: string, updates: Partial<Shot>) => void;
  sceneAssets?: Record<string, SceneAsset>;
}

const SHOT_SIZES: Shot['shotSize'][] = [
  'Extreme Close-up', 'Close-up', 'Medium Close-up', 'Medium Shot',
  'Medium Wide', 'Wide Shot', 'Extreme Wide', 'Over-the-Shoulder', 'POV', 'Two-Shot',
];

const CAMERA_MOVEMENTS: Shot['cameraMovement'][] = [
  'Dolly In', 'Dolly Out', 'Pan Right', 'Pan Left', 'Tilt Up', 'Tilt Down',
  'Static', 'Handheld', 'Tracking', 'Crane Up', 'Crane Down', 'Zoom In', 'Zoom Out',
];

const StoryboardTab: React.FC<StoryboardTabProps> = ({
  shots, parsedScript, selectedShotId, onSelectShot, onUpdateShot,
  sceneAssets = {},
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<Partial<Shot>>({});

  // ── Group shots by sceneId, preserving script's scene order ─────────────
  type ShotGroup = { sceneId: string; scene: Scene | undefined; shots: Shot[] };
  const groupedShots: ShotGroup[] = useMemo(() => {
    const map = new Map<string, ShotGroup>();
    for (const shot of shots) {
      const scene = parsedScript?.scenes.find(s => s.id === shot.sceneId);
      let group = map.get(shot.sceneId);
      if (!group) {
        group = { sceneId: shot.sceneId, scene, shots: [] };
        map.set(shot.sceneId, group);
      }
      group.shots.push(shot);
    }
    const order = (parsedScript?.scenes ?? []).map(s => s.id);
    return [...map.entries()]
      .sort(([a], [b]) => {
        const ia = order.indexOf(a);
        const ib = order.indexOf(b);
        // 已知场景按剧本顺序，未知场景排在末尾
        if (ia === -1 && ib === -1) return 0;
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return ia - ib;
      })
      .map(([, group]) => group);
  }, [shots, parsedScript]);

  // helper: turn raw base64 into a usable src (handles both with/without prefix)
  const toImgSrc = (b64: string | undefined): string | null => {
    if (!b64) return null;
    return b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`;
  };

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
      {/* Shot grid — grouped by scene with cinematic storyboard headers */}
      <div className="flex-1 p-4 overflow-auto space-y-6">
        {groupedShots.map(({ sceneId, scene, shots: sceneShots }) => {
          const sceneAsset = sceneAssets[sceneId];
          const heroThumb = toImgSrc(sceneAsset?.keyframeImages?.wide);
          return (
            <section key={sceneId}>
              {/* Cinematic storyboard section header */}
              <header className="flex items-center gap-3 mb-3 px-1">
                <span className="text-[10px] uppercase tracking-widest text-gray-500 font-semibold">
                  Scene
                </span>
                <h2 className="text-base font-semibold text-gray-100">
                  {scene?.location || sceneId}
                </h2>
                {scene?.time && (
                  <span className="text-xs text-gray-400 bg-gray-800 px-2 py-0.5 rounded">
                    {scene.time}
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  · {sceneShots.length} 镜
                </span>
                <div className="flex-1 h-px bg-gradient-to-r from-gray-700 to-transparent" />
              </header>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {sceneShots.map(shot => {
                  const chars = (parsedScript?.characters || []).filter(
                    c => shot.characters.includes(c.id),
                  );

                  return (
                    <div
                      key={shot.id}
                      onClick={() => onSelectShot(shot.id === selectedShotId ? null : shot.id)}
                      onDoubleClick={() => {
                        onSelectShot(shot.id);
                        setEditForm({
                          shotSize: shot.shotSize,
                          cameraMovement: shot.cameraMovement,
                          durationSeconds: shot.durationSeconds,
                          actionSummary: shot.actionSummary,
                          dialogue: shot.dialogue,
                        });
                        setIsEditing(true);
                      }}
                      className={`p-3 rounded-lg border cursor-pointer transition-all select-none ${
                        shot.id === selectedShotId
                          ? 'border-cyan-400 bg-cyan-950/40 shadow-[0_0_0_1px_rgba(34,211,238,0.5)]'
                          : 'border-gray-700 bg-gray-900 hover:border-gray-500 hover:shadow'
                      }`}
                    >
                      {/* Shot-level thumbnail: prefer shot's own sceneAsset.wide,
                          fall back to the section hero thumb, finally placeholder. */}
                      {(() => {
                        const shotAsset = sceneAssets[shot.sceneId];
                        const thumb = toImgSrc(shotAsset?.keyframeImages?.wide) || heroThumb;
                        return (
                          <div className="aspect-video bg-gray-950 rounded mb-2 overflow-hidden border border-gray-800">
                            {thumb ? (
                              <img
                                src={thumb}
                                alt={`scene ${scene?.location ?? shot.sceneId}`}
                                className="w-full h-full object-cover"
                                loading="lazy"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-600">
                                无预览 · {scene?.location || shot.sceneId}
                              </div>
                            )}
                          </div>
                        );
                      })()}

                      {/* Shot number & badges */}
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-bold text-cyan-300">
                          镜 {shot.shotNumber}
                        </span>
                        <div className="flex gap-1">
                          <span className="text-[10px] px-1.5 py-0.5 bg-gray-800 text-gray-300 rounded truncate max-w-[80px]" title={shot.shotSize}>
                            {shot.shotSize}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded truncate max-w-[70px]" title={shot.cameraMovement}>
                            {shot.cameraMovement}
                          </span>
                        </div>
                      </div>

                      {/* Action summary */}
                      <div className="text-sm text-gray-200 mb-2 line-clamp-2">
                        {shot.actionSummary || shot.visualPrompts.actionPrompt}
                      </div>

                      {/* Characters */}
                      <div className="flex flex-wrap gap-1 mb-2">
                        {chars.slice(0, 3).map(c => (
                          <span key={c.id} className="text-[10px] px-1.5 py-0.5 bg-emerald-900/50 text-emerald-300 rounded">
                            {c.name}
                          </span>
                        ))}
                        {chars.length > 3 && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded">
                            +{chars.length - 3}
                          </span>
                        )}
                      </div>

                      {/* Duration */}
                      <div className="text-xs text-gray-400 flex items-center gap-1">
                        <span>{shot.durationSeconds}s</span>
                        {shot.dialogue && <span className="text-amber-400 ml-1">对白</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>

      {/* Shot detail panel */}
      {selectedShot && (
        <div className="w-96 border-l border-gray-700 bg-gray-900 p-4 overflow-auto flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-bold text-gray-100">
              镜 {selectedShot.shotNumber}
            </h3>
            <div className="flex gap-2">
              {isEditing ? (
                <>
                  <button
                    onClick={() => {
                      onUpdateShot(selectedShot.id, editForm);
                      setIsEditing(false);
                      setEditForm({});
                    }}
                    className="px-3 py-1 text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded transition-colors"
                  >
                    保存
                  </button>
                  <button
                    onClick={() => {
                      setIsEditing(false);
                      setEditForm({});
                    }}
                    className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 rounded transition-colors"
                  >
                    取消
                  </button>
                </>
              ) : (
                <button
                  onClick={() => {
                    setEditForm({
                      shotSize: selectedShot.shotSize,
                      cameraMovement: selectedShot.cameraMovement,
                      durationSeconds: selectedShot.durationSeconds,
                      actionSummary: selectedShot.actionSummary,
                      dialogue: selectedShot.dialogue,
                    });
                    setIsEditing(true);
                  }}
                  className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
                >
                  编辑
                </button>
              )}
            </div>
          </div>

          <div className="space-y-3 flex-1">
            {/* Shot size */}
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">景别</label>
              {isEditing ? (
                <select
                  value={editForm.shotSize ?? selectedShot.shotSize}
                  onChange={e => setEditForm(f => ({ ...f, shotSize: e.target.value as Shot['shotSize'] }))}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 text-gray-100 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
                >
                  {SHOT_SIZES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              ) : (
                <div className="text-sm text-gray-100">{selectedShot.shotSize}</div>
              )}
            </div>

            {/* Camera movement */}
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">运镜</label>
              {isEditing ? (
                <select
                  value={editForm.cameraMovement ?? selectedShot.cameraMovement}
                  onChange={e => setEditForm(f => ({ ...f, cameraMovement: e.target.value as Shot['cameraMovement'] }))}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 text-gray-100 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
                >
                  {CAMERA_MOVEMENTS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : (
                <div className="text-sm text-gray-200">{selectedShot.cameraMovement}</div>
              )}
            </div>

            {/* Duration */}
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">时长 (秒)</label>
              {isEditing ? (
                <input
                  type="number"
                  min={0.5}
                  max={30}
                  step={0.5}
                  value={editForm.durationSeconds ?? selectedShot.durationSeconds}
                  onChange={e => setEditForm(f => ({ ...f, durationSeconds: parseFloat(e.target.value) || 3 }))}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 text-gray-100 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
                />
              ) : (
                <div className="text-sm text-gray-200">{selectedShot.durationSeconds}s</div>
              )}
            </div>

            {/* Action summary */}
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">动作描述</label>
              {isEditing ? (
                <textarea
                  rows={2}
                  value={editForm.actionSummary ?? selectedShot.actionSummary}
                  onChange={e => setEditForm(f => ({ ...f, actionSummary: e.target.value }))}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 text-gray-100 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400 resize-none"
                />
              ) : (
                <div className="text-sm text-gray-200">{selectedShot.actionSummary || '-'}</div>
              )}
            </div>

            {/* Dialogue */}
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">对白</label>
              {isEditing ? (
                <textarea
                  rows={2}
                  value={editForm.dialogue ?? selectedShot.dialogue}
                  onChange={e => setEditForm(f => ({ ...f, dialogue: e.target.value }))}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 text-gray-100 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400 resize-none italic"
                />
              ) : (
                selectedShot.dialogue ? (
                  <div className="text-sm text-gray-200 italic">{selectedShot.dialogue}</div>
                ) : (
                  <div className="text-sm text-gray-500">—</div>
                )
              )}
            </div>

            {/* Scene prompts (read-only) */}
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">场景提示词</label>
              <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs whitespace-pre-wrap">
                {selectedShot.visualPrompts.scenePrompt || selectedShot.keyframeStartPrompt || '-'}
              </pre>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">动作提示词</label>
              <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs whitespace-pre-wrap">
                {selectedShot.visualPrompts.actionPrompt || '-'}
              </pre>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1">相机提示词</label>
              <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs">
                {selectedShot.visualPrompts.cameraPrompt || '-'}
              </pre>
            </div>

            {(selectedShot.keyframeStartPrompt || selectedShot.keyframeEndPrompt) && (
              <>
                <div>
                  <label className="text-xs font-medium text-gray-400 block mb-1">起始帧提示词</label>
                  <pre className="mt-1 p-2 bg-gray-950 border border-gray-700 text-gray-200 rounded text-xs">
                    {selectedShot.keyframeStartPrompt || '-'}
                  </pre>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-400 block mb-1">结束帧提示词</label>
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
  onGenerateVariation: (charId: string, prompt: string, projectId?: string) => Promise<void>;
  isGenerating: Record<string, boolean>;
  selectedCharId: string | null;
  onSelectChar: (id: string | null) => void;
  onUpdatePrompt: (charId: string, prompt: string) => void;
  onResolvePrompt: (charIds?: string[]) => Promise<void>;
  isResolvingPrompts: boolean;
}

type PromptSource = 'none' | 'auto' | 'manual';

// Tiny visual chip that makes the prompt provenance obvious in the UI.
const PromptSourceBadge: React.FC<{ source: PromptSource }> = ({ source }) => {
  const map: Record<PromptSource, { label: string; cls: string }> = {
    none:   { label: '空',       cls: 'bg-gray-800 text-gray-400' },
    auto:   { label: 'AI 自动',  cls: 'bg-cyan-900/40 text-cyan-300 border border-cyan-700/40' },
    manual: { label: '人工编辑', cls: 'bg-amber-900/40 text-amber-300 border border-amber-700/40' },
  };
  const { label, cls } = map[source];
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${cls}`}>{label}</span>;
};

const CharactersTab: React.FC<CharactersTabProps> = ({
  characters, characterAssets, onGenerateThreeView, onGenerateVariation,
  isGenerating, selectedCharId, onSelectChar, onUpdatePrompt,
  onResolvePrompt, isResolvingPrompts,
}) => {
  const [editingPrompt, setEditingPrompt] = useState<Record<string, string>>({});
  const char = characters.find(c => c.id === selectedCharId);
  const asset = selectedCharId ? characterAssets[selectedCharId] : undefined;
  // Resolve order: user edit buffer > parsedScript.characters[i].visualPrompt
  //                > characterAssets[id].visualPrompt (legacy fallback for
  //                older sessions before the bidirectional hydration added
  //                in 2026-08).
  const promptValue = editingPrompt[selectedCharId ?? '']
    ?? char?.visualPrompt
    ?? asset?.visualPrompt
    ?? '';
  const promptSource: PromptSource = editingPrompt[selectedCharId ?? '']
    ? 'manual'
    : (char?.visualPrompt || asset?.visualPrompt) ? 'auto' : 'none';

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
            const preview = asset?.visualPrompt || char.visualPrompt;
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
                {/* Bidirectional prompt preview: show as italic line-clamp-2
                    when present; falling back to a 'generating...' hint while
                    autoResolvePrompts is in flight. */}
                {preview ? (
                  <div
                    className="mt-2 text-[10px] text-gray-500 line-clamp-2 italic"
                    title={preview}
                  >
                    {preview}
                  </div>
                ) : isResolvingPrompts ? (
                  <div className="mt-2 text-[10px] text-cyan-500/70 italic">
                    正在生成提示词…
                  </div>
                ) : null}
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

            {/* Generate three-view button */}
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

            {/* ── Visual prompt (bidirectional) ─────────────────────────── */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold text-gray-200">视觉提示词</h3>
                <PromptSourceBadge source={promptSource} />
              </div>
              <textarea
                className="w-full p-2 bg-gray-950 border border-gray-700 text-gray-100 placeholder:text-gray-500 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
                rows={4}
                value={promptValue}
                placeholder="点击下方「生成初始提示词」开始，或等待解析后自动生成…"
                onChange={e => {
                  if (!selectedCharId) return;
                  setEditingPrompt(prev => ({ ...prev, [selectedCharId]: e.target.value }));
                  onUpdatePrompt(selectedCharId, e.target.value);
                }}
              />
              <div className="flex flex-wrap gap-2 mt-2">
                {/* Input side: from script analysis → prompt box */}
                <button
                  onClick={() => onResolvePrompt([char.id])}
                  disabled={isResolvingPrompts}
                  className="px-3 py-1 bg-cyan-700 hover:bg-cyan-600 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                  title="让 LLM 根据角色属性生成视觉提示词"
                >
                  {char.visualPrompt || asset?.visualPrompt
                    ? '重新生成提示词'
                    : '生成初始提示词'}
                </button>
                {/* Output side 1: prompt box → image generation (three-view) */}
                <button
                  onClick={() => onGenerateThreeView(char.id)}
                  disabled={isGenerating[char.id] || !promptValue}
                  className="px-3 py-1 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                  title="使用当前提示词生成三视图"
                >
                  用此提示词生成三视图
                </button>
                {/* Output side 2: prompt box → variation */}
                <button
                  onClick={() => onGenerateVariation(char.id, promptValue)}
                  disabled={isGenerating[char.id] || !promptValue}
                  className="px-3 py-1 bg-purple-700 hover:bg-purple-600 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                  title="把当前提示词作为种子生成服装变体"
                >
                  以此为种子生成变体
                </button>
              </div>
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

                <div className="text-xs text-gray-400 mb-2">
                  <details className="group">
                    <summary className="cursor-pointer hover:text-gray-200 line-clamp-1 list-none">
                      <span className="text-gray-500 mr-1 group-open:hidden">▸</span>
                      <span className="text-gray-500 mr-1 hidden group-open:inline">▾</span>
                      {shot.visualPrompts.actionPrompt}
                    </summary>
                    <pre className="mt-1 p-2 bg-gray-950 border border-gray-800 rounded text-[11px] whitespace-pre-wrap text-gray-300">
                      <b className="text-emerald-400">动作：</b>{shot.visualPrompts.actionPrompt}
                      {'\n'}<b className="text-cyan-400">场景：</b>{shot.visualPrompts.scenePrompt}
                      {'\n'}<b className="text-purple-400">相机：</b>{shot.visualPrompts.cameraPrompt}
                      {shot.visualPrompts.transitionPrompt
                        ? `\n转场：${shot.visualPrompts.transitionPrompt}`
                        : ''}
                    </pre>
                  </details>
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

// ==============================
// Tab: Scenes — list + keyframe grid per scene
// ==============================

interface ScenesTabProps {
  parsedScript: ScriptData | null;
  sceneAssets: Record<string, SceneAsset>;
  isGeneratingSceneAsset: Record<string, boolean>;
  selectedSceneId: string | null;
  onSelectScene: (id: string | null) => void;
  onGenerateSceneAsset: (
    sceneId: string,
    location: string,
    time: string,
    atmosphere: string,
    visualPrompt: string,
    projectId?: string,
  ) => Promise<void>;
  onUpdatePrompt: (sceneId: string, prompt: string) => void;
  onResolvePrompt: (sceneIds?: string[]) => Promise<void>;
}

const ScenesTab: React.FC<ScenesTabProps> = ({
  parsedScript, sceneAssets, isGeneratingSceneAsset,
  selectedSceneId, onSelectScene, onGenerateSceneAsset,
  onUpdatePrompt, onResolvePrompt,
}) => {
  const scenes = parsedScript?.scenes ?? [];

  if (scenes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <p>解析剧本后查看场景</p>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Scene list */}
      <div className="w-64 border-r border-gray-700 p-4 overflow-auto">
        <h3 className="text-sm font-semibold text-gray-200 mb-3">场景列表</h3>
        <div className="space-y-2">
          {scenes.map(scene => {
            const asset = sceneAssets[scene.id];
            const doneCount = asset
              ? Object.values(asset.keyframeImages ?? {}).filter(Boolean).length
              : 0;
            const preview = scene.visualPrompt || asset?.visualPrompt;
            return (
              <div
                key={scene.id}
                onClick={() => onSelectScene(scene.id === selectedSceneId ? null : scene.id)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  scene.id === selectedSceneId
                    ? 'border-cyan-400 bg-cyan-950/40'
                    : 'border-gray-700 bg-gray-900 hover:border-gray-500'
                }`}
              >
                <div className="font-medium text-sm text-gray-100">{scene.location}</div>
                <div className="text-xs text-gray-400">{scene.time}</div>
                {doneCount > 0 && (
                  <div className="text-xs text-emerald-400 mt-1">✓ {doneCount}/3 已生成</div>
                )}
                {/* Bidirectional preview line (mirrors CharactersTab) */}
                {preview ? (
                  <div
                    className="mt-2 text-[10px] text-gray-500 line-clamp-2 italic"
                    title={preview}
                  >
                    {preview}
                  </div>
                ) : scene.atmosphere ? (
                  <div
                    className="mt-2 text-[10px] text-gray-600 line-clamp-2 italic"
                    title={scene.atmosphere}
                  >
                    {scene.atmosphere}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {/* Scene detail */}
      {selectedSceneId ? (() => {
        const scene = scenes.find(s => s.id === selectedSceneId);
        if (!scene) return null;
        const asset = sceneAssets[scene.id];
        const generating = !!isGeneratingSceneAsset[scene.id];
        const keyframes = ['wide', 'closeup', 'mood'] as const;

        // Resolve chain: parsedScript.scenes[i].visualPrompt (single source
        // of truth, hydrated by pollAutoSceneAsset / generateSceneAsset /
        // resolveSceneVisualPrompts) → asset fallback for legacy sessions
        // → atmosphere as last-resort minimum.
        const promptValue = scene.visualPrompt || asset?.visualPrompt || scene.atmosphere || '';

        return (
          <div className="flex-1 p-4 overflow-auto">
            <div className="mb-4">
              <h2 className="text-xl font-bold text-gray-100">{scene.location}</h2>
              <p className="text-sm text-gray-400">
                {scene.time} | {scene.atmosphere || '未指定氛围'}
              </p>
            </div>

            {/* ── Visual prompt (bidirectional) ─────────────────────────── */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold text-gray-200">视觉提示词</h3>
                <PromptSourceBadge
                  source={scene.visualPrompt || asset?.visualPrompt ? 'auto' : 'none'}
                />
              </div>
              <textarea
                className="w-full p-2 bg-gray-950 border border-gray-700 text-gray-100 placeholder:text-gray-500 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
                rows={4}
                value={promptValue}
                placeholder="点击下方「生成初始提示词」开始，或等待解析后自动生成…"
                onChange={e => onUpdatePrompt(scene.id, e.target.value)}
              />
              <div className="flex flex-wrap gap-2 mt-2">
                {/* Input side: derive scene prompt from location/time/atmosphere */}
                <button
                  onClick={() => onResolvePrompt([scene.id])}
                  className="px-3 py-1 bg-cyan-700 hover:bg-cyan-600 text-white text-xs rounded-lg transition-colors"
                  title="基于场景位置/时间/氛围生成视觉提示词"
                >
                  {scene.visualPrompt || asset?.visualPrompt
                    ? '重新生成提示词'
                    : '生成初始提示词'}
                </button>
                {/* Output side: prompt box → keyframe image generation */}
                <button
                  onClick={() =>
                    onGenerateSceneAsset(
                      scene.id,
                      scene.location,
                      scene.time,
                      scene.atmosphere || '',
                      promptValue,
                    )
                  }
                  disabled={generating || !promptValue}
                  className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                  title="使用当前提示词生成关键帧"
                >
                  用此提示词生成关键帧
                </button>
              </div>
            </div>

            {/* Keyframe grid */}
            {asset?.keyframeImages && (
              <div>
                <h3 className="text-sm font-semibold text-gray-200 mb-2">关键帧</h3>
                <div className="grid grid-cols-3 gap-3">
                  {keyframes.map(k => {
                    const b64 = asset.keyframeImages?.[k];
                    return (
                      <div key={k} className="text-center">
                        <div className="text-xs text-gray-400 mb-1 capitalize">{k}</div>
                        {b64 ? (
                          <img
                            src={`data:image/png;base64,${b64}`}
                            alt={k}
                            className="w-full aspect-video object-cover rounded border border-gray-700"
                          />
                        ) : (
                          <div className="w-full aspect-video bg-gray-800 border border-gray-700 rounded flex items-center justify-center text-gray-500 text-xs">
                            未生成
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Variations */}
                {asset.variations && asset.variations.length > 0 && (
                  <div className="mt-4">
                    <h3 className="text-sm font-semibold text-gray-200 mb-2">变体</h3>
                    <div className="grid grid-cols-4 gap-2">
                      {asset.variations.map(v => (
                        <div key={v.id} className="bg-gray-800/60 border border-gray-700 rounded-lg p-2">
                          <div className="text-xs text-gray-400 mb-1">{v.name}</div>
                          {v.image && (
                            <img
                              src={`data:image/png;base64,${v.image}`}
                              alt={v.name}
                              className="w-full aspect-video object-cover rounded"
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })() : (
        <div className="flex-1 flex items-center justify-center text-gray-500">
          选择左侧场景查看详情
        </div>
      )}
    </div>
  );
};