// ─────────────────────────────────────────────────────────────────────────────
// SettingsPanel — top-right toolbar gear button + dropdown panel.
//
// Redesigned with Cloud/Local tabs for per-component mode switching.
// Each tab contains settings for LLM, VLM, Image, and Video independently,
// allowing mixed configurations (e.g. Cloud LLM + Local VLM).
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useRef, useState } from 'react';
import { Settings, X, Image as ImageIcon, Video, Key, RefreshCw, Check, AlertCircle, Cpu, Cloud, HardDrive, Download, ChevronDown } from 'lucide-react';
import { useSettingsStore } from '../store/useSettingsStore';
import type { ModelDownloadState, ModelDownloadStatus } from '../store/useSettingsStore';
import type { RuntimeSettings } from '../services/settingsService';

// ── Model options ──────────────────────────────────────────────────────────────

const DASHSCOPE_LLM_OPTIONS = [
  { value: 'qwen3.7-max', label: 'qwen3.7-max (最强推理)' },
  { value: 'qwen3.7-plus', label: 'qwen3.7-plus (平衡性能)' },
  { value: 'qwen3.6-flash', label: 'qwen3.6-flash (快速响应)' },
];

const DASHSCOPE_VLM_OPTIONS = [
  { value: 'qwen3-vl-flash-2026-01-22', label: 'qwen3-vl-flash-2026-01-22 (推荐)' },
  { value: 'qwen-vl-plus', label: 'qwen-vl-plus (高精度)' },
  { value: 'qwen-vl-max', label: 'qwen-vl-max (最强)' },
];

const DASHSCOPE_IMAGE_OPTIONS = [
  { value: 'wan2.7-image-pro', label: 'wan2.7-image-pro (推荐)' },
  { value: 'wan2.1-imageedit', label: 'wan2.1-imageedit' },
];

const LOCAL_LLM_OPTIONS = [
  { value: 'qwen2.5-7b-q4_k_m', label: 'Qwen2.5-7B-Q4_K_M (当前本地)' },
  { value: 'qwen3.5-9b', label: 'Qwen3.5-9B' },
  { value: 'qwen3.5-32b', label: 'Qwen3.5-32B' },
];

const DTYPE_OPTIONS = [
  { value: 'bfloat16', label: 'bfloat16 (推荐)' },
  { value: 'float16', label: 'float16' },
  { value: 'float32', label: 'float32' },
];

const VIDEO_PROVIDER_OPTIONS = [
  { value: 'dashscope', label: 'DashScope (云端)' },
  { value: 'local_wan', label: 'Local Wan2.1' },
  { value: 'svd', label: 'Stable Video Diffusion' },
];

const IMAGE_MODEL_PRESETS = [
  'Tongyi-MAI/Z-Image-Turbo',
  'Tongyi-MAI/Z-Image',
  'stabilityai/stable-diffusion-xl-base-1.0',
];

// ── Component ─────────────────────────────────────────────────────────────────

export function SettingsPanel() {
  const open = useSettingsStore((s) => s.open);
  const toggleOpen = useSettingsStore((s) => s.toggleOpen);
  const setOpen = useSettingsStore((s) => s.setOpen);
  const settings = useSettingsStore((s) => s.settings);
  const loading = useSettingsStore((s) => s.loading);
  const saving = useSettingsStore((s) => s.saving);
  const error = useSettingsStore((s) => s.error);
  const hasFetched = useSettingsStore((s) => s.hasFetched);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  const fetchModelDownloads = useSettingsStore((s) => s.fetchModelDownloads);
  const saveSettings = useSettingsStore((s) => s.saveSettings);
  const setLocalField = useSettingsStore((s) => s.setLocalField);
  const modelDownloads = useSettingsStore((s) => s.modelDownloads);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  // Sync active tab with current model_mode setting
  const activeTab = settings.model_mode === 'local' ? 'local' : 'cloud';

  const handleTabChange = (tab: 'cloud' | 'local') => {
    const mode = tab === 'cloud' ? 'cloud' : 'local';
    setLocalField('vlm_mode', mode);
    setLocalField('image_mode', mode);
    setLocalField('video_mode', mode);
    setLocalField('model_mode', mode);
  };

  // Preset buttons — "Pure Cloud" forces every component to cloud.
  // "Pure Local" forces every component to local. "Custom" lets the user mix.
  const applyPureCloud = () => {
    setLocalField('vlm_mode', 'cloud');
    setLocalField('image_mode', 'cloud');
    setLocalField('video_mode', 'cloud');
    setLocalField('model_mode', 'cloud');
  };

  const applyPureLocal = () => {
    setLocalField('vlm_mode', 'local');
    setLocalField('image_mode', 'local');
    setLocalField('video_mode', 'local');
    setLocalField('model_mode', 'local');
  };

  // First open: hydrate from server and model download status
  useEffect(() => {
    if (open && !hasFetched && !loading) {
      fetchSettings();
      fetchModelDownloads();
    }
  }, [open, hasFetched, loading, fetchSettings, fetchModelDownloads]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, [open, setOpen]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, setOpen]);

  const handleSave = async () => {
    await saveSettings({
      model_mode: settings.model_mode,
      vlm_mode: settings.vlm_mode,
      image_mode: settings.image_mode,
      video_mode: settings.video_mode,
      dashscope_llm_model: settings.dashscope_llm_model,
      dashscope_vlm_model: settings.dashscope_vlm_model,
      dashscope_image_model: settings.dashscope_image_model,
      llm_base_url: settings.llm_base_url,
      llm_model: settings.llm_model,
      image_model_id: settings.image_model_id,
      image_dtype: settings.image_dtype,
      video_provider: settings.video_provider,
      dashscope_llm_api_key: settings.dashscope_llm_api_key ?? '',
      dashscope_vlm_api_key: settings.dashscope_vlm_api_key ?? '',
      dashscope_image_api_key: settings.dashscope_image_api_key ?? '',
      dashscope_video_api_key: settings.dashscope_video_api_key ?? '',
    });
    if (!useSettingsStore.getState().error) {
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 1800);
    }
  };

  return (
    <div className="relative" ref={rootRef}>
      {/* Trigger button (gear icon) */}
      <button
        type="button"
        onClick={toggleOpen}
        title="Runtime settings"
        className={`p-2 rounded-lg transition-colors ${
          open
            ? 'bg-gray-700 text-white'
            : 'hover:bg-gray-800 text-gray-300 hover:text-white'
        }`}
      >
        <Settings size={18} />
      </button>

      {/* Panel */}
      {open && (
        <div
          className="absolute right-0 top-full mt-2 z-40 w-[380px] max-h-[85vh] overflow-y-auto
            bg-gray-900 border border-gray-700 rounded-xl shadow-2xl
            text-sm text-gray-200"
          onMouseDown={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <div className="flex items-center gap-2">
              <Settings size={16} className="text-blue-400" />
              <span className="font-semibold text-white">Settings</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => { fetchSettings(); fetchModelDownloads(); }}
                title="Reload from server"
                disabled={loading}
                className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-40"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                title="Close"
                className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Error banner */}
          {error && (
            <div className="flex items-start gap-2 mx-4 mt-3 px-3 py-2 rounded bg-red-950/40 border border-red-800/60 text-xs text-red-300">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span className="break-all">{error}</span>
            </div>
          )}

          {/* Tab bar */}
          <div className="flex items-center justify-between border-b border-gray-700 px-2 pt-2">
            <div className="flex">
              <TabButton
                active={activeTab === 'cloud'}
                onClick={() => handleTabChange('cloud')}
                icon={<Cloud size={12} />}
                label="Cloud"
              />
              <TabButton
                active={activeTab === 'local'}
                onClick={() => handleTabChange('local')}
                icon={<HardDrive size={12} />}
                label="Local"
              />
            </div>
            <div className="flex items-center gap-1 pr-2">
              <PresetButton
                label="纯云端"
                onClick={applyPureCloud}
                active={
                  settings.vlm_mode === 'cloud' &&
                  settings.image_mode === 'cloud' &&
                  settings.video_mode === 'cloud'
                }
              />
              <PresetButton
                label="全本地"
                onClick={applyPureLocal}
                active={
                  settings.vlm_mode === 'local' &&
                  settings.image_mode === 'local' &&
                  settings.video_mode === 'local'
                }
              />
            </div>
          </div>

          {/* Tab content */}
          <div className="p-4">
            {activeTab === 'cloud' && (
              <CloudTabContent settings={settings} setLocalField={setLocalField} />
            )}
            {activeTab === 'local' && (
              <LocalTabContent
                settings={settings}
                setLocalField={setLocalField}
                modelDownloads={modelDownloads}
              />
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-gray-700 bg-gray-950/40">
            <button
              type="button"
              onClick={() => { fetchSettings(); fetchModelDownloads(); }}
              disabled={loading || saving}
              className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1.5 rounded
                disabled:opacity-40 transition-colors"
            >
              Reset
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || loading}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors
                ${savedFlash
                  ? 'bg-emerald-600 text-white'
                  : 'bg-blue-600 hover:bg-blue-500 text-white active:scale-95'}
                disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {saving ? (
                <>
                  <RefreshCw size={12} className="animate-spin" />
                  Saving...
                </>
              ) : savedFlash ? (
                <>
                  <Check size={12} />
                  Saved
                </>
              ) : (
                'Save'
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab button ────────────────────────────────────────────────────────────────

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-lg border-b-2 transition-colors
        ${active
          ? 'border-blue-500 text-blue-400 bg-blue-950/30'
          : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800'
        }`}
    >
      {icon}
      {label}
    </button>
  );
}

// ── Preset button (compact, in tab bar) ────────────────────────────────────────

function PresetButton({
  label,
  onClick,
  active,
}: {
  label: string;
  onClick: () => void;
  active: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={`应用 ${label} 预设`}
      className={`px-2 py-1 rounded text-[10px] font-medium border transition-colors
        ${active
          ? 'bg-blue-600 border-blue-500 text-white'
          : 'bg-gray-800/60 border-gray-700 text-gray-400 hover:text-white hover:bg-gray-700/80 hover:border-gray-600'
        }`}
    >
      {label}
    </button>
  );
}

// ── Mode toggle (cloud/local segmented control) ────────────────────────────────

function ModeToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: 'cloud' | 'local';
  onChange: (v: 'cloud' | 'local') => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] text-gray-300">{label}</span>
      <div className="flex rounded-md overflow-hidden border border-gray-700 text-[10px]">
        <button
          type="button"
          onClick={() => onChange('cloud')}
          className={`flex items-center gap-1 px-2.5 py-1 transition-colors
            ${value === 'cloud'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800'
            }`}
        >
          <Cloud size={10} />
          Cloud
        </button>
        <button
          type="button"
          onClick={() => onChange('local')}
          className={`flex items-center gap-1 px-2.5 py-1 transition-colors
            ${value === 'local'
              ? 'bg-emerald-600 text-white'
              : 'bg-gray-900 text-gray-400 hover:text-gray-200 hover:bg-gray-800'
            }`}
        >
          <HardDrive size={10} />
          Local
        </button>
      </div>
    </div>
  );
}

// ── Cloud tab content ──────────────────────────────────────────────────────────

function CloudTabContent({
  settings,
  setLocalField,
}: {
  settings: RuntimeSettings;
  setLocalField: <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {/* Per-component mode toggles — explicit, so users can mix */}
      <SettingsGroup
        icon={<Cloud size={14} className="text-blue-400" />}
        title="Per-Component Mode"
      >
        <p className="text-[10px] text-gray-500 leading-relaxed -mt-1">
          纯云端 + 几个必须本地（Depth / SAM2 / Grounding DINO / LaMa）。
          下方可单独覆盖每个组件的运行方式。
        </p>
        <ModeToggle
          label="VLM (场景分析)"
          value={settings.vlm_mode}
          onChange={(v) => setLocalField('vlm_mode', v)}
        />
        <ModeToggle
          label="Image (图像生成)"
          value={settings.image_mode}
          onChange={(v) => setLocalField('image_mode', v)}
        />
        <ModeToggle
          label="Video (视频生成)"
          value={settings.video_mode}
          onChange={(v) => setLocalField('video_mode', v)}
        />
        <div className="flex items-start gap-1.5 px-2 py-1.5 rounded bg-amber-950/30 border border-amber-800/40 text-[10px] text-amber-300/90">
          <HardDrive size={11} className="mt-0.5 shrink-0" />
          <span>
            以下组件始终本地运行（无云端替代）：Depth / SAM2 / Grounding DINO / LaMa。
          </span>
        </div>
      </SettingsGroup>

      {/* LLM Settings */}
      <SettingsGroup icon={<Cpu size={14} className="text-indigo-400" />} title="LLM">
        <Field label="Model">
          <select
            value={settings.dashscope_llm_model}
            onChange={(e) => setLocalField('dashscope_llm_model', e.target.value)}
            className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
              focus:outline-none focus:border-blue-500"
          >
            {DASHSCOPE_LLM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="API Key">
          <input
            type="password"
            value={settings.dashscope_llm_api_key ?? ''}
            onChange={(e) => setLocalField('dashscope_llm_api_key', e.target.value)}
            placeholder="sk-..."
            spellCheck={false}
            className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
              placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
        </Field>
      </SettingsGroup>

      {/* VLM Settings */}
      {settings.vlm_mode === 'cloud' && (
        <SettingsGroup icon={<Video size={14} className="text-cyan-400" />} title="VLM (Cloud)">
          <Field label="Model">
            <select
              value={settings.dashscope_vlm_model}
              onChange={(e) => setLocalField('dashscope_vlm_model', e.target.value)}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                focus:outline-none focus:border-blue-500"
            >
              {DASHSCOPE_VLM_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="API Key">
            <input
              type="password"
              value={settings.dashscope_vlm_api_key ?? ''}
              onChange={(e) => setLocalField('dashscope_vlm_api_key', e.target.value)}
              placeholder="sk-..."
              spellCheck={false}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </Field>
        </SettingsGroup>
      )}

      {/* Image Settings */}
      {settings.image_mode === 'cloud' && (
        <SettingsGroup icon={<ImageIcon size={14} className="text-emerald-400" />} title="Image (Cloud)">
          <Field label="Model">
            <select
              value={settings.dashscope_image_model}
              onChange={(e) => setLocalField('dashscope_image_model', e.target.value)}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                focus:outline-none focus:border-blue-500"
            >
              {DASHSCOPE_IMAGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="API Key">
            <input
              type="password"
              value={settings.dashscope_image_api_key ?? ''}
              onChange={(e) => setLocalField('dashscope_image_api_key', e.target.value)}
              placeholder="sk-..."
              spellCheck={false}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </Field>
        </SettingsGroup>
      )}

      {/* Video Settings */}
      {settings.video_mode === 'cloud' && (
        <SettingsGroup icon={<Video size={14} className="text-purple-400" />} title="Video (Cloud)">
          <Field label="Provider">
            <select
              value={settings.video_provider}
              onChange={(e) => setLocalField('video_provider', e.target.value)}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                focus:outline-none focus:border-blue-500"
            >
              {VIDEO_PROVIDER_OPTIONS.filter((o) => o.value === 'dashscope').map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="API Key">
            <input
              type="password"
              value={settings.dashscope_video_api_key ?? ''}
              onChange={(e) => setLocalField('dashscope_video_api_key', e.target.value)}
              placeholder="sk-..."
              spellCheck={false}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </Field>
        </SettingsGroup>
      )}

      <p className="text-[10px] text-gray-500 leading-relaxed">
        纯云端模式：LLM / VLM / 图像 / 视频走 DashScope API。需要有效 API Key。
      </p>
    </div>
  );
}

// ── Local tab content ──────────────────────────────────────────────────────────

function LocalTabContent({
  settings,
  setLocalField,
  modelDownloads,
}: {
  settings: RuntimeSettings;
  setLocalField: <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => void;
  modelDownloads: ModelDownloadState;
}) {
  return (
    <div className="flex flex-col gap-3">
      {/* Per-component mode toggles */}
      <SettingsGroup
        icon={<HardDrive size={14} className="text-emerald-400" />}
        title="Per-Component Mode"
      >
        <p className="text-[10px] text-gray-500 leading-relaxed -mt-1">
          每个组件可独立切换 cloud / local。需要本地运行时，请确保下方对应模型已下载。
        </p>
        <ModeToggle
          label="VLM (场景分析)"
          value={settings.vlm_mode}
          onChange={(v) => setLocalField('vlm_mode', v)}
        />
        <ModeToggle
          label="Image (图像生成)"
          value={settings.image_mode}
          onChange={(v) => setLocalField('image_mode', v)}
        />
        <ModeToggle
          label="Video (视频生成)"
          value={settings.video_mode}
          onChange={(v) => setLocalField('video_mode', v)}
        />
        <div className="flex items-start gap-1.5 px-2 py-1.5 rounded bg-amber-950/30 border border-amber-800/40 text-[10px] text-amber-300/90">
          <HardDrive size={11} className="mt-0.5 shrink-0" />
          <span>
            始终本地运行：Depth / SAM2 / Grounding DINO / LaMa — 无云端替代。
          </span>
        </div>
      </SettingsGroup>

      {/* LLM Settings */}
      <SettingsGroup icon={<Cpu size={14} className="text-indigo-400" />} title="Local LLM">
        <Field label="Server URL">
          <input
            type="text"
            value={settings.llm_base_url}
            onChange={(e) => setLocalField('llm_base_url', e.target.value)}
            placeholder="http://localhost:8080/v1"
            spellCheck={false}
            className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
              placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
        </Field>
        <Field label="Model">
          <select
            value={settings.llm_model}
            onChange={(e) => setLocalField('llm_model', e.target.value)}
            className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
              focus:outline-none focus:border-blue-500"
          >
            {LOCAL_LLM_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
      </SettingsGroup>

      {/* VLM local settings — only shown if VLM mode is local */}
      {settings.vlm_mode === 'local' && (
        <SettingsGroup icon={<Video size={14} className="text-cyan-400" />} title="Local VLM">
          <ModelDownloadItem
            modelKey="qwen3vl"
            label="Qwen3-VL"
            hint="场景分析 VLM"
            status={modelDownloads.qwen3vl}
          />
        </SettingsGroup>
      )}

      {/* Image local settings — only shown if Image mode is local */}
      {settings.image_mode === 'local' && (
        <SettingsGroup icon={<ImageIcon size={14} className="text-emerald-400" />} title="Local Image Generation">
          <Field label="Model ID">
            <input
              type="text"
              value={settings.image_model_id}
              onChange={(e) => setLocalField('image_model_id', e.target.value)}
              placeholder="Tongyi-MAI/Z-Image-Turbo"
              list="local-image-presets"
              spellCheck={false}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
            <datalist id="local-image-presets">
              {IMAGE_MODEL_PRESETS.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </Field>
          <Field label="Dtype">
            <select
              value={settings.image_dtype}
              onChange={(e) => setLocalField('image_dtype', e.target.value)}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                focus:outline-none focus:border-blue-500"
            >
              {DTYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
          <ModelDownloadItem
            modelKey="image"
            label="Z-Image-Turbo"
            hint="图生图 (~33 GB)"
            status={modelDownloads.image}
          />
        </SettingsGroup>
      )}

      {/* Video local settings — only shown if Video mode is local */}
      {settings.video_mode === 'local' && (
        <SettingsGroup icon={<Video size={14} className="text-purple-400" />} title="Local Video Generation">
          <Field label="Provider">
            <select
              value={settings.video_provider}
              onChange={(e) => setLocalField('video_provider', e.target.value)}
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                focus:outline-none focus:border-blue-500"
            >
              {VIDEO_PROVIDER_OPTIONS.filter((o) => o.value !== 'dashscope').map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
        </SettingsGroup>
      )}

      {/* Always-local components — download UI */}
      <SettingsGroup icon={<Download size={14} className="text-amber-400" />} title="Always-Local Models">
        <p className="text-[10px] text-gray-500 leading-relaxed -mt-1">
          以下模型没有云端替代品，始终在本地运行。请提前下载。
        </p>
        <ModelDownloadItem
          modelKey="depth"
          label="Depth (DepthAnything V2)"
          hint="深度估计"
          status={modelDownloads.depth}
        />
        <ModelDownloadItem
          modelKey="sam2"
          label="SAM2"
          hint="图像分割"
          status={modelDownloads.sam2}
        />
        <ModelDownloadItem
          modelKey="grounding_dino"
          label="Grounding DINO"
          hint="目标检测"
          status={modelDownloads.grounding_dino}
        />
        <ModelDownloadItem
          modelKey="lama"
          label="LaMa Inpaint"
          hint="图像修复"
          status={modelDownloads.lama}
        />
      </SettingsGroup>

      <p className="text-[10px] text-gray-500 leading-relaxed">
        本地模式需要本地运行 llama-server / 下载模型权重。请确保有足够显存（推荐 16GB+）。
      </p>
    </div>
  );
}

// ── Settings group ─────────────────────────────────────────────────────────────

function SettingsGroup({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-950/60 p-3">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">{title}</span>
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

// ── Field ─────────────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-gray-500">{label}</span>
      {children}
    </label>
  );
}

// ── Model download item ────────────────────────────────────────────────────────

function ModelDownloadItem({
  modelKey,
  label,
  hint,
  status,
}: {
  modelKey: keyof ModelDownloadState;
  label: string;
  hint: string;
  status: string;
}) {
  const setModelDownloadStatus = useSettingsStore((s) => s.setModelDownloadStatus);

  return (
    <div className="flex items-center justify-between gap-2 px-2 py-1.5 rounded bg-gray-900/60 border border-gray-700/50">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-xs text-gray-200 truncate">{label}</span>
        <span className="text-[10px] text-gray-500 truncate">{hint}</span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {status === 'downloading' && (
          <RefreshCw size={12} className="text-blue-400 animate-spin" />
        )}
        {status === 'downloaded' && (
          <Check size={12} className="text-emerald-400" />
        )}
        {status === 'error' && (
          <AlertCircle size={12} className="text-red-400" />
        )}
        <button
          type="button"
          onClick={() => triggerDownload(modelKey, setModelDownloadStatus)}
          disabled={status === 'downloading' || status === 'downloaded'}
          className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors
            ${status === 'downloaded'
              ? 'bg-emerald-900/40 text-emerald-400 cursor-default'
              : status === 'downloading'
              ? 'bg-blue-900/40 text-blue-400 cursor-wait'
              : 'bg-indigo-700/60 hover:bg-indigo-600 text-white'
            }`}
        >
          {status === 'downloaded' ? '已下载' : status === 'downloading' ? '下载中...' : <><Download size={10} /> 下载</>}
        </button>
      </div>
    </div>
  );
}

// Module-level polling state — prevents stacked timers for the same model
const _pollTimers: Map<keyof ModelDownloadState, ReturnType<typeof setTimeout>> = new Map();

async function triggerDownload(
  modelKey: keyof ModelDownloadState,
  setModelDownloadStatus: (model: keyof ModelDownloadState, status: ModelDownloadStatus) => void
) {
  const backend = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

  // Cancel any existing poll for this model
  const existing = _pollTimers.get(modelKey);
  if (existing !== undefined) {
    clearTimeout(existing);
    _pollTimers.delete(modelKey);
  }

  try {
    setModelDownloadStatus(modelKey as keyof ModelDownloadState, 'downloading');
    const resp = await fetch(`${backend}/api/aicss/models/download/${modelKey}`, { method: 'POST' });
    if (!resp.ok) throw new Error(await resp.text());

    // Poll until terminal state or safety timeout (30 min)
    const safetyTimeout = 30 * 60 * 1000;
    const pollInterval = 2000;
    const deadline = Date.now() + safetyTimeout;

    const poll = async () => {
      try {
        await useSettingsStore.getState().fetchModelDownloads();
        const current = useSettingsStore.getState().modelDownloads[modelKey];
        if (current === 'downloaded' || current === 'error') {
          _pollTimers.delete(modelKey);
          return;
        }
        if (Date.now() >= deadline) {
          console.warn(`[ModelDownload] Safety timeout reached for ${modelKey}`);
          setModelDownloadStatus(modelKey as keyof ModelDownloadState, 'error');
          _pollTimers.delete(modelKey);
          return;
        }
        const timer = setTimeout(poll, pollInterval);
        _pollTimers.set(modelKey, timer);
      } catch {
        // Network error during polling — stop and let the next manual retry handle it
        _pollTimers.delete(modelKey);
      }
    };

    const timer = setTimeout(poll, pollInterval);
    _pollTimers.set(modelKey, timer);
  } catch (e) {
    console.error(`[ModelDownload] Trigger failed for ${modelKey}:`, e);
    setModelDownloadStatus(modelKey as keyof ModelDownloadState, 'error');
  }
}
