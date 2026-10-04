// ─────────────────────────────────────────────────────────────────────────────
// LightingPanel (T13) — 情绪→光照自动映射 + 三灯微调面板
//
// 功能：
//   1. 6 套预设缩略图按钮（与后端 presets/lighting/*.json 同名），点击设 lightingPreset
//   2. 场景类型 × 情绪组合下拉，自动选预设
//   3. 每个灯（key/fill/rim）的 energy 滑块、color 取色器、location 三轴微调
//   4. "应用" 按钮：把当前编辑结果写入 store（lightingPreset + lightingCustom），
//      Viewer3D 据此重渲染
//
// 设计：本地维护一份编辑副本 `draft`，所有微调改 draft；点应用才 commit 到 store。
// 这样可避免拖动滑块时每帧都触发 store 更新与 Viewer3D 重渲染。
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useMemo, useState } from 'react';
import { Sun, Square, Lightbulb, Sliders, X, Check, RefreshCw } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import {
  LIGHTING_PRESETS,
  MOOD_OPTIONS,
  MOOD_TO_PRESET,
  rgbToHex,
  hexToRgb,
  clonePreset,
  type LightingPreset,
  type LightSpec,
} from '../lighting/presets';

type LightRole = 'key' | 'fill' | 'rim';

const ROLE_LABEL: Record<LightRole, string> = {
  key: '主光 (Key)',
  fill: '补光 (Fill)',
  rim: '边缘光 (Rim)',
};

const ROLE_ICON: Record<LightRole, typeof Sun> = {
  key: Sun,
  fill: Square,
  rim: Lightbulb,
};

// 预设缩略图配色（用 key/fill/rim 三色做渐变示意）
function PresetSwatch({ presetName }: { presetName: string }) {
  const p = LIGHTING_PRESETS[presetName];
  if (!p) return <div className="w-full h-8 rounded bg-gray-800" />;
  const k = rgbToHex(p.key.color);
  const f = rgbToHex(p.fill.color);
  const r = rgbToHex(p.rim.color);
  return (
    <div
      className="w-full h-8 rounded border border-gray-700"
      style={{ background: `linear-gradient(90deg, ${k} 0%, ${k} 33%, ${f} 33%, ${f} 66%, ${r} 66%, ${r} 100%)` }}
    />
  );
}

interface LightingPanelProps {
  /** 是否默认展开。默认 false（折叠为按钮）。 */
  defaultOpen?: boolean;
}

export function LightingPanel({ defaultOpen = false }: LightingPanelProps = {}) {
  const lightingPreset = useAppStore((s) => s.lightingPreset);
  const lightingCustom = useAppStore((s) => s.lightingCustom);
  const setLightingPreset = useAppStore((s) => s.setLightingPreset);
  const setLightingCustom = useAppStore((s) => s.setLightingCustom);

  const [open, setOpen] = useState(defaultOpen);

  // 当前选中的预设名（本地编辑状态，未 commit 前可能与 store 不同）
  const [draftPreset, setDraftPreset] = useState<string | null>(lightingPreset);
  // 当前编辑中的预设副本（含三灯微调）
  const [draft, setDraft] = useState<LightingPreset | null>(lightingCustom);

  // 当外部 store 变化（例如 reset）时同步本地 draft
  useEffect(() => {
    setDraftPreset(lightingPreset);
    setDraft(lightingCustom);
  }, [lightingPreset, lightingCustom]);

  // 选预设 / 切 mood → 加载该预设的灯规格到 draft
  const loadPreset = (name: string | null) => {
    setDraftPreset(name);
    if (name && LIGHTING_PRESETS[name]) {
      setDraft(clonePreset(LIGHTING_PRESETS[name]));
    } else {
      setDraft(null);
    }
  };

  const handlePresetClick = (name: string) => {
    loadPreset(name);
  };

  const handleMoodChange = (moodValue: string) => {
    const presetName = MOOD_TO_PRESET[moodValue];
    if (presetName) loadPreset(presetName);
  };

  // 微调单个灯的某个字段
  const updateLight = (role: LightRole, patch: Partial<LightSpec>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, [role]: { ...prev[role], ...patch } };
    });
  };

  const updateLightColor = (role: LightRole, hex: string) => {
    updateLight(role, { color: hexToRgb(hex) });
  };

  const updateLightLocation = (role: LightRole, axis: 0 | 1 | 2, value: number) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const base = prev[role].location ?? [0, 0, 0];
      const next: [number, number, number] = [base[0], base[1], base[2]];
      next[axis] = value;
      return { ...prev, [role]: { ...prev[role], location: next } };
    });
  };

  // 应用：commit 到 store，Viewer3D 据此重渲染
  const handleApply = () => {
    setLightingPreset(draftPreset);
    setLightingCustom(draft);
  };

  // 重置：清空 preset 与 custom，Viewer3D 回退到硬编码默认灯
  const handleReset = () => {
    setDraftPreset(null);
    setDraft(null);
    setLightingPreset(null);
    setLightingCustom(null);
  };

  // 当前 mood（用于下拉显示）— 根据 draftPreset 反查
  const currentMood = useMemo(() => {
    if (!draftPreset) return '';
    const found = MOOD_OPTIONS.find((o) => o.preset === draftPreset);
    return found ? found.value : '';
  }, [draftPreset]);

  // 是否有未提交的改动（用于应用按钮高亮）
  const dirty = draftPreset !== lightingPreset || draft !== lightingCustom;

  return (
    <div className="absolute top-3 left-3 z-30 select-none">
      {/* 触发按钮 */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="光照预设"
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
          open
            ? 'bg-amber-600 text-white'
            : 'bg-gray-900/90 text-amber-200 hover:bg-gray-800 border border-amber-800/40'
        }`}
      >
        <Sun size={14} />
        <span>光照</span>
        {draftPreset && (
          <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-900/60 text-[10px] text-amber-100">
            {LIGHTING_PRESETS[draftPreset]?.name ?? draftPreset}
          </span>
        )}
      </button>

      {/* 展开面板 */}
      {open && (
        <div
          className="mt-2 w-[320px] max-h-[80vh] overflow-y-auto
            bg-gray-900/95 backdrop-blur border border-gray-700 rounded-xl shadow-2xl
            text-sm text-gray-200"
          onMouseDown={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-700">
            <div className="flex items-center gap-2">
              <Sliders size={14} className="text-amber-400" />
              <span className="font-semibold text-white text-xs">光照预设</span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
              title="收起"
            >
              <X size={14} />
            </button>
          </div>

          <div className="p-3 flex flex-col gap-3">
            {/* 6 套预设缩略图 */}
            <div>
              <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">预设</div>
              <div className="grid grid-cols-3 gap-1.5">
                {Object.keys(LIGHTING_PRESETS).map((name) => {
                  const active = draftPreset === name;
                  return (
                    <button
                      key={name}
                      type="button"
                      onClick={() => handlePresetClick(name)}
                      title={LIGHTING_PRESETS[name].description}
                      className={`flex flex-col gap-1 p-1.5 rounded-lg border transition-all ${
                        active
                          ? 'border-amber-500 bg-amber-900/30'
                          : 'border-gray-700 bg-gray-950/60 hover:border-gray-500'
                      }`}
                    >
                      <PresetSwatch presetName={name} />
                      <span className={`text-[10px] leading-tight ${active ? 'text-amber-200' : 'text-gray-400'}`}>
                        {LIGHTING_PRESETS[name].name}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 场景类型 × 情绪组合下拉 */}
            <div>
              <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">场景 × 情绪</div>
              <select
                value={currentMood}
                onChange={(e) => handleMoodChange(e.target.value)}
                className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                  focus:outline-none focus:border-amber-500"
              >
                <option value="">— 手动选预设 —</option>
                {MOOD_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label} → {LIGHTING_PRESETS[o.preset]?.name ?? o.preset}
                  </option>
                ))}
              </select>
            </div>

            {/* 三灯微调 */}
            {draft && draftPreset ? (
              <div className="flex flex-col gap-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">灯参数</div>
                {(['key', 'fill', 'rim'] as LightRole[]).map((role) => {
                  const light = draft[role];
                  const Icon = ROLE_ICON[role];
                  return (
                    <div key={role} className="rounded-lg border border-gray-700 bg-gray-950/60 p-2">
                      <div className="flex items-center gap-1.5 mb-2">
                        <Icon size={12} className="text-amber-300" />
                        <span className="text-[11px] font-medium text-gray-200">{ROLE_LABEL[role]}</span>
                        <span className="ml-auto text-[9px] text-gray-500 uppercase">{light.type}</span>
                      </div>

                      {/* Energy 滑块 */}
                      <label className="flex flex-col gap-1 mb-1.5">
                        <div className="flex items-center justify-between text-[10px] text-gray-400">
                          <span>能量</span>
                          <span className="text-amber-300">{light.energy.toFixed(2)}</span>
                        </div>
                        <input
                          type="range"
                          min={0}
                          max={10}
                          step={0.1}
                          value={light.energy}
                          onChange={(e) => updateLight(role, { energy: Number(e.target.value) })}
                          className="w-full accent-amber-400"
                        />
                      </label>

                      {/* Color 取色器 */}
                      <label className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-[10px] text-gray-400">颜色</span>
                        <input
                          type="color"
                          value={rgbToHex(light.color)}
                          onChange={(e) => updateLightColor(role, e.target.value)}
                          className="w-8 h-6 rounded bg-transparent border border-gray-700 cursor-pointer p-0"
                        />
                      </label>

                      {/* Location 三轴（可选） */}
                      {light.location && (
                        <div className="grid grid-cols-3 gap-1">
                          {([0, 1, 2] as const).map((axis) => (
                            <label key={axis} className="flex flex-col gap-0.5">
                              <span className="text-[9px] text-gray-500">{['X', 'Y', 'Z'][axis]}</span>
                              <input
                                type="number"
                                step={0.5}
                                value={light.location![axis]}
                                onChange={(e) => updateLightLocation(role, axis, Number(e.target.value))}
                                className="w-full px-1 py-0.5 rounded bg-gray-900 border border-gray-700 text-gray-100 text-[10px]
                                  focus:outline-none focus:border-amber-500"
                              />
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-[11px] text-gray-500 bg-gray-950/40 rounded px-2 py-1.5">
                未选预设 — Viewer3D 使用硬编码默认灯。点上方预设或下拉选择以应用光照。
              </div>
            )}

            {/* 应用 / 重置 */}
            <div className="flex items-center gap-2 pt-1 border-t border-gray-700">
              <button
                type="button"
                onClick={handleApply}
                disabled={!draftPreset || !dirty}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors
                  ${dirty && draftPreset
                    ? 'bg-amber-600 hover:bg-amber-500 text-white active:scale-95'
                    : 'bg-gray-700 text-gray-500 cursor-not-allowed'}`}
              >
                <Check size={12} />
                应用
              </button>
              <button
                type="button"
                onClick={handleReset}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-gray-400 hover:text-gray-200
                  hover:bg-gray-800 transition-colors"
              >
                <RefreshCw size={12} />
                重置
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
