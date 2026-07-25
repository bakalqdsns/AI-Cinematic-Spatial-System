// ─────────────────────────────────────────────────────────────────────────────
// SettingsPanel — top-right toolbar gear button + dropdown panel.
//
// Lets the user switch the LLM endpoint / model, image model, dtype, video
// provider and DashScope API key at runtime. All changes are POSTed to the
// backend's `/api/aicss/settings` endpoint and hot-reload the service
// singletons (local_llm, image_generator) on the server side.
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useRef, useState } from 'react';
import { Settings, X, Server, Image as ImageIcon, Video, Key, RefreshCw, Check, AlertCircle, Cpu } from 'lucide-react';
import { useSettingsStore } from '../store/useSettingsStore';

const DTYPE_OPTIONS = [
  { value: 'bfloat16', label: 'bfloat16 (recommended)' },
  { value: 'float16', label: 'float16' },
  { value: 'float32', label: 'float32' },
];

const VIDEO_PROVIDER_OPTIONS = [
  { value: 'dashscope', label: 'DashScope (cloud)' },
  { value: 'local_wan', label: 'Local Wan2.1' },
  { value: 'svd', label: 'Stable Video Diffusion' },
];

const IMAGE_MODEL_PRESETS = [
  'stabilityai/stable-diffusion-xl-base-1.0',
  'Tongyi-MAI/Z-Image',
];

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
  const saveSettings = useSettingsStore((s) => s.saveSettings);
  const setLocalField = useSettingsStore((s) => s.setLocalField);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  // First open: hydrate from server
  useEffect(() => {
    if (open && !hasFetched && !loading) {
      fetchSettings();
    }
  }, [open, hasFetched, loading, fetchSettings]);

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
    const before = settings;
    await saveSettings({
      llm_base_url: settings.llm_base_url,
      llm_model: settings.llm_model,
      image_model_id: settings.image_model_id,
      image_dtype: settings.image_dtype,
      video_provider: settings.video_provider,
      dashscope_api_key: settings.dashscope_api_key ?? '',
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
          className="absolute right-0 top-full mt-2 z-40 w-[360px] max-h-[80vh] overflow-y-auto
            bg-gray-900 border border-gray-700 rounded-xl shadow-2xl
            text-sm text-gray-200"
          onMouseDown={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <div className="flex items-center gap-2">
              <Settings size={16} className="text-blue-400" />
              <span className="font-semibold text-white">Runtime Settings</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => fetchSettings()}
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

          {/* Body */}
          <div className="flex flex-col gap-3 p-4">
            {error && (
              <div className="flex items-start gap-2 px-3 py-2 rounded bg-red-950/40 border border-red-800/60 text-xs text-red-300">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span className="break-all">{error}</span>
              </div>
            )}

            {/* LLM section */}
            <Section icon={<Server size={14} className="text-blue-400" />} title="Local LLM (llama.cpp)">
              <Field label="Base URL">
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
              <Field label="Model name">
                <input
                  type="text"
                  value={settings.llm_model}
                  onChange={(e) => setLocalField('llm_model', e.target.value)}
                  placeholder="qwen3.5-9b"
                  spellCheck={false}
                  className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                    placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
              </Field>
            </Section>

            {/* Image model section */}
            <Section icon={<ImageIcon size={14} className="text-emerald-400" />} title="Image Generation">
              <Field label="Model ID">
                <input
                  type="text"
                  value={settings.image_model_id}
                  onChange={(e) => setLocalField('image_model_id', e.target.value)}
                  placeholder="stabilityai/stable-diffusion-xl-base-1.0"
                  list="image-model-presets"
                  spellCheck={false}
                  className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                    placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
                <datalist id="image-model-presets">
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
            </Section>

            {/* Video provider section */}
            <Section icon={<Video size={14} className="text-purple-400" />} title="Video Provider">
              <div className="flex flex-col gap-1">
                {VIDEO_PROVIDER_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors
                      ${settings.video_provider === opt.value
                        ? 'bg-blue-950/50 border border-blue-700/50'
                        : 'hover:bg-gray-800 border border-transparent'}`}
                  >
                    <input
                      type="radio"
                      name="video_provider"
                      value={opt.value}
                      checked={settings.video_provider === opt.value}
                      onChange={() => setLocalField('video_provider', opt.value)}
                      className="accent-blue-500"
                    />
                    <span className="text-xs text-gray-200">{opt.label}</span>
                  </label>
                ))}
              </div>
            </Section>

            {/* API key section */}
            <Section icon={<Key size={14} className="text-amber-400" />} title="API Keys">
              <Field label="DashScope API Key (Inpaint / Cloud Video)">
                <input
                  type="password"
                  value={settings.dashscope_api_key ?? ''}
                  onChange={(e) => setLocalField('dashscope_api_key', e.target.value)}
                  placeholder="sk-..."
                  spellCheck={false}
                  className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-100 text-xs
                    placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
              </Field>
            </Section>

            <p className="text-[10px] text-gray-500 leading-relaxed">
              切换 LLM / 图像模型将立即在后端生效（无需重启）。
              <Cpu size={10} className="inline mx-1" />
              下次推理请求会使用新配置。
            </p>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-gray-700 bg-gray-950/40">
            <button
              type="button"
              onClick={() => fetchSettings()}
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

// ── Small helpers ────────────────────────────────────────────────────────────

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-gray-500">{label}</span>
      {children}
    </label>
  );
}
