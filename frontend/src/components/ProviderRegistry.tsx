// ─────────────────────────────────────────────────────────────────────────────
// ProviderRegistry — manage cloud AI providers (DashScope, OpenAI-compatible,
// ToAPIs, SiliconFlow, Groq, custom OpenAI-compatible endpoints).
//
// Each provider entry is a self-contained config block:
//   {
//     name:           string                       (unique key)
//     type:           "dashscope" | "openai_compatible" | ...
//     base_url:       string                       (OpenAI-compat only)
//     api_key:        string
//     extra_headers:  Record<string,string> | null (optional)
//     extra_json:     Record<string,unknown> | null (optional)
//     models: {
//       llm:   string | null    (chat)
//       vlm:   string | null    (vision)
//       image: string | null    (text-to-image)
//       video: string | null    (text-to-video)
//     }
//   }
//
// Adding a new third-party model requires NO backend code change for any
// OpenAI-compatible service — just fill in this form and pick the new
// provider in any module's Provider dropdown.
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2, Edit3, Check, X, Server, Cpu, Image as ImageIcon, Video as VideoIcon, MessageSquare, Loader2 } from 'lucide-react';
import type { ProviderConfig, ProviderTypeInfo } from '../services/settingsService';
import { listProviderTypes, pingProvider } from '../services/settingsService';

interface Props {
  providers: ProviderConfig[];
  onChange: (providers: ProviderConfig[]) => void;
  componentProviders: { llm: string; vlm: string; image: string; video: string };
  onSelectProvider: (component: 'llm' | 'vlm' | 'image' | 'video', providerName: string) => void;
}

const EMPTY_PROVIDER = (): ProviderConfig => ({
  name: '',
  type: 'openai_compatible',
  base_url: 'https://api.example.com/v1',
  api_key: '',
  extra_headers: null,
  extra_json: null,
  models: { llm: null, vlm: null, image: null, video: null },
});

const SUPPORTED_TYPES = [
  { value: 'openai_compatible', label: 'OpenAI 兼容 (ToAPIs / SiliconFlow / Groq / 自建...)', needsBaseUrl: true },
  { value: 'dashscope', label: 'DashScope (通义千问)', needsBaseUrl: false },
];

export function ProviderRegistry({ providers, onChange, componentProviders, onSelectProvider }: Props) {
  const [editing, setEditing] = useState<ProviderConfig | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [types, setTypes] = useState<ProviderTypeInfo[]>([]);
  const [pingStatus, setPingStatus] = useState<Record<string, 'idle' | 'pinging' | 'ok' | 'fail'>>({});

  useEffect(() => {
    listProviderTypes().then(setTypes).catch(() => setTypes([]));
  }, []);

  const upsert = (p: ProviderConfig) => {
    if (!p.name.trim()) return;
    const existing = providers.findIndex((x) => x.name === p.name);
    const next = [...providers];
    if (existing >= 0) next[existing] = p;
    else next.push(p);
    onChange(next);
  };

  const remove = (name: string) => {
    onChange(providers.filter((p) => p.name !== name));
  };

  const startNew = () => {
    setEditing(EMPTY_PROVIDER());
    setIsNew(true);
  };

  const startEdit = (p: ProviderConfig) => {
    setEditing({ ...p, models: { ...p.models }, extra_headers: p.extra_headers ? { ...p.extra_headers } : null });
    setIsNew(false);
  };

  const tryPing = async (p: ProviderConfig) => {
    setPingStatus((s) => ({ ...s, [p.name]: 'pinging' }));
    try {
      const comp = (Object.entries(p.models).find(([, v]) => v)?.[0] as 'llm' | 'vlm' | 'image' | 'video') || 'llm';
      const ok = await pingProvider(comp, p.name);
      setPingStatus((s) => ({ ...s, [p.name]: ok ? 'ok' : 'fail' }));
    } catch {
      setPingStatus((s) => ({ ...s, [p.name]: 'fail' }));
    }
  };

  return (
    <div className="space-y-3">
      {/* List */}
      <div className="space-y-1.5">
        {providers.length === 0 && (
          <div className="text-xs text-gray-500 italic px-2 py-3 text-center border border-dashed border-gray-700 rounded">
            尚未添加任何云端 Provider。点击下方"新增"添加第一个。
          </div>
        )}
        {providers.map((p) => {
          const isActive = Object.values(componentProviders).includes(p.name);
          const status = pingStatus[p.name] || 'idle';
          return (
            <div
              key={p.name}
              className={`p-2.5 rounded border ${
                isActive ? 'border-blue-600/60 bg-blue-950/20' : 'border-gray-700 bg-gray-900'
              } flex flex-col gap-1.5`}
            >
              <div className="flex items-center gap-2">
                <Server size={12} className="text-blue-400 shrink-0" />
                <span className="text-sm font-semibold text-gray-100">{p.name}</span>
                <span className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">{p.type}</span>
                {isActive && (
                  <span className="text-[10px] text-blue-300 bg-blue-900/50 px-1.5 py-0.5 rounded">使用中</span>
                )}
                <div className="flex-1" />
                {status === 'pinging' && <Loader2 size={12} className="animate-spin text-gray-400" />}
                {status === 'ok' && <Check size={12} className="text-green-400" />}
                {status === 'fail' && <X size={12} className="text-red-400" />}
                <button
                  onClick={() => tryPing(p)}
                  className="text-[10px] text-gray-400 hover:text-blue-300 px-1.5"
                  title="测试连接"
                >
                  测试
                </button>
                <button
                  onClick={() => startEdit(p)}
                  className="text-gray-400 hover:text-blue-300"
                  title="编辑"
                >
                  <Edit3 size={12} />
                </button>
                <button
                  onClick={() => remove(p.name)}
                  className="text-gray-400 hover:text-red-400"
                  title="删除"
                >
                  <Trash2 size={12} />
                </button>
              </div>

              {/* Model assignments */}
              <div className="flex flex-wrap gap-1.5 text-[10px]">
                {(['llm', 'vlm', 'image', 'video'] as const).map((comp) => {
                  const m = p.models[comp];
                  if (!m) return null;
                  const Icon = comp === 'llm' ? MessageSquare : comp === 'vlm' ? Cpu : comp === 'image' ? ImageIcon : VideoIcon;
                  const isSelected = componentProviders[comp] === p.name;
                  return (
                    <button
                      key={comp}
                      onClick={() => onSelectProvider(comp, p.name)}
                      className={`flex items-center gap-1 px-1.5 py-0.5 rounded border transition-colors ${
                        isSelected
                          ? 'border-blue-500 bg-blue-900/40 text-blue-200'
                          : 'border-gray-700 text-gray-400 hover:border-gray-500'
                      }`}
                      title={isSelected ? '当前使用此 Provider' : '设为该模块的 Provider'}
                    >
                      <Icon size={10} />
                      <span className="uppercase">{comp}</span>
                      <span className="text-gray-500 max-w-[120px] truncate">{m}</span>
                    </button>
                  );
                })}
              </div>

              {p.base_url && (
                <div className="text-[10px] text-gray-500 font-mono truncate">{p.base_url}</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add button */}
      {!editing && (
        <button
          onClick={startNew}
          className="w-full px-3 py-1.5 text-xs rounded border border-dashed border-gray-600
            text-gray-300 hover:border-blue-500 hover:text-blue-300 flex items-center justify-center gap-1.5"
        >
          <Plus size={12} /> 新增 Provider
        </button>
      )}

      {/* Editor */}
      {editing && (
        <ProviderEditor
          provider={editing}
          isNew={isNew}
          types={types}
          onCancel={() => setEditing(null)}
          onSave={(p) => {
            upsert(p);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

// ── Inline editor ─────────────────────────────────────────────────────────────

function ProviderEditor({
  provider,
  isNew,
  types,
  onCancel,
  onSave,
}: {
  provider: ProviderConfig;
  isNew: boolean;
  types: ProviderTypeInfo[];
  onCancel: () => void;
  onSave: (p: ProviderConfig) => void;
}) {
  const [draft, setDraft] = useState<ProviderConfig>(provider);

  const needsBaseUrl = useMemo(
    () => SUPPORTED_TYPES.find((t) => t.value === draft.type)?.needsBaseUrl ?? true,
    [draft.type],
  );

  const setModel = (k: keyof ProviderConfig['models'], v: string) => {
    setDraft((d) => ({ ...d, models: { ...d.models, [k]: v || null } }));
  };

  const trySave = () => {
    if (!draft.name.trim()) return;
    onSave(draft);
  };

  return (
    <div className="p-3 rounded border border-blue-700/60 bg-gray-900 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-blue-300">
          {isNew ? '新增 Provider' : `编辑: ${provider.name}`}
        </span>
        <div className="flex gap-1">
          <button onClick={onCancel} className="text-xs text-gray-400 hover:text-gray-200 px-2 py-0.5">
            取消
          </button>
          <button onClick={trySave} className="text-xs text-blue-300 hover:text-blue-100 px-2 py-0.5 flex items-center gap-1">
            <Check size={11} /> 保存
          </button>
        </div>
      </div>

      {/* Name */}
      <Field label="名称 (唯一标识)">
        <input
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '_') })}
          placeholder="toapi / siliconflow / myproxy"
          className="w-full px-2 py-1 rounded bg-gray-950 border border-gray-700 text-xs text-gray-100 focus:outline-none focus:border-blue-500"
        />
      </Field>

      {/* Type */}
      <Field label="类型">
        <select
          value={draft.type}
          onChange={(e) => setDraft({ ...draft, type: e.target.value })}
          className="w-full px-2 py-1 rounded bg-gray-950 border border-gray-700 text-xs text-gray-100 focus:outline-none focus:border-blue-500"
        >
          {SUPPORTED_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </Field>

      {/* Base URL */}
      {needsBaseUrl && (
        <Field label="Base URL">
          <input
            value={draft.base_url}
            onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
            placeholder="https://api.example.com/v1"
            className="w-full px-2 py-1 rounded bg-gray-950 border border-gray-700 text-xs text-gray-100 focus:outline-none focus:border-blue-500 font-mono"
          />
        </Field>
      )}

      {/* API Key */}
      <Field label="API Key">
        <input
          type="password"
          value={draft.api_key ?? ''}
          onChange={(e) => setDraft({ ...draft, api_key: e.target.value })}
          placeholder="sk-..."
          className="w-full px-2 py-1 rounded bg-gray-950 border border-gray-700 text-xs text-gray-100 focus:outline-none focus:border-blue-500"
        />
      </Field>

      {/* Models */}
      <Field label="模型分配">
        <div className="grid grid-cols-2 gap-1.5">
          {(['llm', 'vlm', 'image', 'video'] as const).map((comp) => {
            const label = { llm: 'LLM (对话)', vlm: 'VLM (视觉)', image: 'Image (生图)', video: 'Video (生视频)' }[comp];
            const Icon = comp === 'llm' ? MessageSquare : comp === 'vlm' ? Cpu : comp === 'image' ? ImageIcon : VideoIcon;
            return (
              <div key={comp} className="flex items-center gap-1.5">
                <Icon size={10} className="text-gray-500 shrink-0" />
                <input
                  value={draft.models[comp] ?? ''}
                  onChange={(e) => setModel(comp, e.target.value)}
                  placeholder={label}
                  className="flex-1 min-w-0 px-2 py-1 rounded bg-gray-950 border border-gray-700 text-[10px] text-gray-100 focus:outline-none focus:border-blue-500 font-mono"
                />
              </div>
            );
          })}
        </div>
        <div className="text-[10px] text-gray-500 mt-1">
          留空表示该 Provider 不支持此能力。模型 ID 由对应服务的文档决定。
        </div>
      </Field>

      {/* Advanced: Extra Headers / JSON */}
      <details className="text-xs">
        <summary className="text-gray-400 cursor-pointer hover:text-blue-300">高级 (Extra Headers / JSON)</summary>
        <div className="mt-2 space-y-2">
          <Field label="Extra Headers (JSON)">
            <textarea
              value={draft.extra_headers ? JSON.stringify(draft.extra_headers, null, 2) : ''}
              onChange={(e) => {
                try {
                  const v = e.target.value.trim();
                  setDraft({ ...draft, extra_headers: v ? JSON.parse(v) : null });
                } catch { /* ignore parse errors until valid */ }
              }}
              placeholder={'{"X-App-Id": "..."}'}
              rows={2}
              className="w-full px-2 py-1 rounded bg-gray-950 border border-gray-700 text-[10px] text-gray-100 focus:outline-none focus:border-blue-500 font-mono"
            />
          </Field>
          <Field label="Extra JSON (merged into requests)">
            <textarea
              value={draft.extra_json ? JSON.stringify(draft.extra_json, null, 2) : ''}
              onChange={(e) => {
                try {
                  const v = e.target.value.trim();
                  setDraft({ ...draft, extra_json: v ? JSON.parse(v) : null });
                } catch { /* ignore */ }
              }}
              placeholder={'{"response_format": "json"}'}
              rows={2}
              className="w-full px-2 py-1 rounded bg-gray-950 border border-gray-700 text-[10px] text-gray-100 focus:outline-none focus:border-blue-500 font-mono"
            />
          </Field>
        </div>
      </details>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] text-gray-400 mb-1 uppercase tracking-wide">{label}</div>
      {children}
    </div>
  );
}
