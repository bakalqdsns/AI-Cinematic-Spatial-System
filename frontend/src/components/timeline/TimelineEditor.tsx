// ─────────────────────────────────────────────────────────────────────────────
// AICSS Timeline Editor — multi-track timeline for the compose pipeline (T03).
//
// Features:
//   - Video track: horizontal list of ShotClip cards, drag-to-reorder using
//     native HTML5 drag-and-drop (no extra deps).
//   - Click a card to select it; selected card shows a delete button.
//   - Top toolbar: transition kind dropdown, transition duration input,
//     「合成」button, progress bar.
//   - Audio track row: list audio clips, add BGM/SFX/voice by path.
//   - Output area: when `outputUrl` is set, render a `<video controls>` so the
//     composed MP4 can be played back inline.
//
// Two exports:
//   - `<TimelineEditor>` — accepts `shots` + `projectId` props (low-level).
//   - `<TimelinePanel>` — reads `useScriptStore` itself, drop-in for a tab.
//
// Integration (do NOT edit ScriptEditor.tsx from this file — see the chat
// response for the exact import + JSX snippet to paste into ScriptEditor).
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useMemo, useState, type DragEvent } from 'react';
import { Trash2, Plus, Film, Music, Loader2, AlertCircle } from 'lucide-react';
import type { Shot } from '../../types/script';
import { useScriptStore } from '../../store/useScriptStore';
import {
  useTimelineStore,
  type ShotClip,
  type AudioTrack,
  type TransitionKind,
} from '../../store/useTimelineStore';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const TRANSITIONS: { value: TransitionKind; label: string }[] = [
  { value: 'cut', label: 'Cut · 硬切' },
  { value: 'dissolve', label: 'Dissolve · 溶解' },
  { value: 'fade', label: 'Fade · 淡入淡出' },
  { value: 'wipe', label: 'Wipe · 擦除' },
];

const AUDIO_TYPES: { value: AudioTrack['type']; label: string }[] = [
  { value: 'bgm', label: 'BGM' },
  { value: 'sfx', label: 'SFX' },
  { value: 'voice', label: 'Voice · 配音' },
];

function formatSeconds(sec: number): string {
  if (!Number.isFinite(sec)) return '—';
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}

// ─── TimelineEditor (low-level, props-driven) ─────────────────────────────────

export interface TimelineEditorProps {
  shots: Shot[];
  projectId: string;
  /** Optional resolver to map a Shot to an absolute MP4 path. Defaults to a
   *  conventional placeholder (see `useTimelineStore.defaultClipPath`). */
  clipPathFor?: (shot: Shot) => string;
}

export function TimelineEditor({ shots, projectId, clipPathFor }: TimelineEditorProps) {
  const {
    tracks,
    audioTracks,
    transition,
    transitionDuration,
    selectedClipId,
    isComposing,
    composeProgress,
    outputUrl,
    error,
    setTracksFromShots,
    moveClip,
    removeClip,
    setTransition,
    setTransitionDuration,
    addAudioTrack,
    removeAudioTrack,
    setSelectedClip,
    compose,
  } = useTimelineStore();

  // Hydrate tracks whenever the incoming `shots` reference changes.
  useEffect(() => {
    setTracksFromShots(shots, clipPathFor);
  }, [shots, clipPathFor, setTracksFromShots]);

  // ─── Drag state (HTML5 DnD) ──────────────────────────────────────────────────
  const [dragFromIdx, setDragFromIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const onDragStart = (e: DragEvent<HTMLDivElement>, idx: number) => {
    setDragFromIdx(idx);
    e.dataTransfer.effectAllowed = 'move';
    // Required for Firefox to actually start the drag.
    e.dataTransfer.setData('text/plain', String(idx));
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>, idx: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverIdx !== idx) setDragOverIdx(idx);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>, idx: number) => {
    e.preventDefault();
    const from = dragFromIdx ?? Number(e.dataTransfer.getData('text/plain'));
    setDragFromIdx(null);
    setDragOverIdx(null);
    if (Number.isNaN(from)) return;
    moveClip(from, idx);
  };

  const onDragEnd = () => {
    setDragFromIdx(null);
    setDragOverIdx(null);
  };

  // ─── Audio add form ──────────────────────────────────────────────────────────
  const [audioType, setAudioType] = useState<AudioTrack['type']>('bgm');
  const [audioPath, setAudioPath] = useState('');
  const [audioStart, setAudioStart] = useState(0);
  const [audioVolume, setAudioVolume] = useState(0.8);

  const addAudio = () => {
    if (!audioPath.trim()) return;
    addAudioTrack({
      id: '',
      type: audioType,
      path: audioPath.trim(),
      startSeconds: Math.max(0, audioStart),
      volume: Math.max(0, Math.min(2, audioVolume)),
    });
    setAudioPath('');
    setAudioStart(0);
  };

  // ─── Derived totals ──────────────────────────────────────────────────────────
  const totalDuration = useMemo(
    () => tracks.reduce((sum, c) => sum + c.durationSec, 0),
    [tracks],
  );

  return (
    <div className="flex flex-col h-full bg-gray-900 text-gray-200 overflow-y-auto">
      {/* ─── Toolbar ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 p-3 border-b border-gray-700 bg-gray-900">
        <div className="flex items-center gap-2">
          <Film size={16} className="text-blue-400" />
          <span className="text-sm font-medium">Timeline</span>
          <span className="text-xs text-gray-500">
            {tracks.length} clips · {formatSeconds(totalDuration)}
          </span>
        </div>

        <div className="flex items-center gap-2 ml-4">
          <label className="text-xs text-gray-400">转场</label>
          <select
            value={transition}
            onChange={(e) => setTransition(e.target.value as TransitionKind)}
            className="px-2 py-1 rounded bg-gray-800 text-sm border border-gray-700"
            disabled={isComposing}
          >
            {TRANSITIONS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400">时长</label>
          <input
            type="number"
            min={0}
            max={5}
            step={0.1}
            value={transitionDuration}
            onChange={(e) => setTransitionDuration(Number(e.target.value) || 0)}
            className="w-20 px-2 py-1 rounded bg-gray-800 text-sm border border-gray-700"
            disabled={isComposing}
          />
          <span className="text-xs text-gray-500">s</span>
        </div>

        <button
          onClick={() => compose(projectId)}
          disabled={isComposing || tracks.length === 0 || !projectId}
          className="ml-auto px-4 py-1.5 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium flex items-center gap-2"
        >
          {isComposing ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              合成中…
            </>
          ) : (
            <>
              <Film size={14} />
              合成
            </>
          )}
        </button>
      </div>

      {/* ─── Progress bar ────────────────────────────────────────────────────── */}
      {(isComposing || composeProgress > 0) && (
        <div className="px-3 py-2 border-b border-gray-700">
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${Math.round(composeProgress * 100)}%` }}
            />
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {isComposing ? '正在合成…' : '合成完成'}
          </div>
        </div>
      )}

      {/* ─── Error ────────────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700 bg-red-900/30 text-red-300 text-sm">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* ─── Video track ─────────────────────────────────────────────────────── */}
      <div className="p-3">
        <div className="text-xs text-gray-500 uppercase mb-2">Video Track</div>
        {tracks.length === 0 ? (
          <div className="text-sm text-gray-600 py-6 text-center">
            暂无镜头。请先生成 shots。
          </div>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-2">
            {tracks.map((clip, idx) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                index={idx}
                selected={selectedClipId === clip.id}
                dragOver={dragOverIdx === idx}
                onSelect={() => setSelectedClip(clip.id)}
                onRemove={() => removeClip(clip.id)}
                onDragStart={(e) => onDragStart(e, idx)}
                onDragOver={(e) => onDragOver(e, idx)}
                onDrop={(e) => onDrop(e, idx)}
                onDragEnd={onDragEnd}
                disabled={isComposing}
              />
            ))}
          </div>
        )}
      </div>

      {/* ─── Audio track ─────────────────────────────────────────────────────── */}
      <div className="p-3 border-t border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <Music size={14} className="text-purple-400" />
          <span className="text-xs text-gray-500 uppercase">Audio Track</span>
        </div>

        <div className="space-y-1 mb-3">
          {audioTracks.length === 0 ? (
            <div className="text-sm text-gray-600 py-2">暂无音频轨。</div>
          ) : (
            audioTracks.map((t) => (
              <AudioClipRow key={t.id} track={t} onRemove={() => removeAudioTrack(t.id)} />
            ))
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 bg-gray-800 p-2 rounded">
          <select
            value={audioType}
            onChange={(e) => setAudioType(e.target.value as AudioTrack['type'])}
            className="px-2 py-1 rounded bg-gray-800 text-sm border border-gray-700"
            disabled={isComposing}
          >
            {AUDIO_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="音频文件路径（绝对路径）"
            value={audioPath}
            onChange={(e) => setAudioPath(e.target.value)}
            className="flex-1 min-w-[200px] px-2 py-1 rounded bg-gray-800 text-sm border border-gray-700"
            disabled={isComposing}
          />
          <input
            type="number"
            min={0}
            step={0.1}
            placeholder="start"
            value={audioStart}
            onChange={(e) => setAudioStart(Number(e.target.value) || 0)}
            className="w-20 px-2 py-1 rounded bg-gray-800 text-sm border border-gray-700"
            disabled={isComposing}
          />
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            placeholder="vol"
            value={audioVolume}
            onChange={(e) => setAudioVolume(Number(e.target.value) || 0)}
            className="w-20 px-2 py-1 rounded bg-gray-800 text-sm border border-gray-700"
            disabled={isComposing}
          />
          <button
            onClick={addAudio}
            disabled={isComposing || !audioPath.trim()}
            className="px-3 py-1 rounded bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm flex items-center gap-1"
          >
            <Plus size={14} />
            添加
          </button>
        </div>
      </div>

      {/* ─── Output ──────────────────────────────────────────────────────────── */}
      <div className="p-3 border-t border-gray-700">
        <div className="text-xs text-gray-500 uppercase mb-2">Output</div>
        {outputUrl ? (
          <div className="space-y-2">
            <video
              controls
              src={outputUrl}
              className="w-full max-h-[360px] rounded bg-black"
            />
            <div className="text-xs text-gray-500 break-all">
              路径: {outputUrl}
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-600 py-4 text-center">
            合成完成后，输出 MP4 将在此处播放。
          </div>
        )}
      </div>
    </div>
  );
}

// ─── ClipCard ──────────────────────────────────────────────────────────────────

interface ClipCardProps {
  clip: ShotClip;
  index: number;
  selected: boolean;
  dragOver: boolean;
  disabled: boolean;
  onSelect: () => void;
  onRemove: () => void;
  onDragStart: (e: DragEvent<HTMLDivElement>) => void;
  onDragOver: (e: DragEvent<HTMLDivElement>) => void;
  onDrop: (e: DragEvent<HTMLDivElement>) => void;
  onDragEnd: () => void;
}

function ClipCard({
  clip,
  index,
  selected,
  dragOver,
  disabled,
  onSelect,
  onRemove,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: ClipCardProps) {
  return (
    <div
      draggable={!disabled}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      onClick={onSelect}
      className={`
        relative flex-shrink-0 w-44 p-2 rounded-lg cursor-move select-none
        border transition-colors
        ${selected
          ? 'bg-blue-900/40 border-blue-500'
          : 'bg-gray-800 border-gray-700 hover:bg-gray-700'}
        ${dragOver ? 'ring-2 ring-blue-400' : ''}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-mono text-gray-500">#{index + 1}</span>
        {selected && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="p-1 rounded hover:bg-red-600 text-red-400 hover:text-white"
            title="删除"
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>
      <div className="text-sm font-medium truncate" title={clip.label}>
        {clip.label}
      </div>
      <div className="text-xs text-gray-500 mt-0.5 truncate" title={clip.clipPath}>
        {clip.clipPath}
      </div>
      <div className="text-xs text-blue-300 mt-1">{formatSeconds(clip.durationSec)}</div>
    </div>
  );
}

// ─── AudioClipRow ─────────────────────────────────────────────────────────────

interface AudioClipRowProps {
  track: AudioTrack;
  onRemove: () => void;
}

function AudioClipRow({ track, onRemove }: AudioClipRowProps) {
  const typeLabel =
    AUDIO_TYPES.find((t) => t.value === track.type)?.label ?? track.type;
  return (
    <div className="flex items-center gap-2 px-2 py-1 rounded bg-gray-800 text-sm">
      <span className="px-1.5 py-0.5 rounded bg-purple-900/60 text-purple-300 text-xs">
        {typeLabel}
      </span>
      <span className="flex-1 truncate" title={track.path}>
        {track.path}
      </span>
      <span className="text-xs text-gray-500">
        @ {formatSeconds(track.startSeconds)} · vol {track.volume.toFixed(2)}
      </span>
      <button
        onClick={onRemove}
        className="p-1 rounded hover:bg-red-600 text-red-400 hover:text-white"
        title="删除"
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}

// ─── TimelinePanel (drop-in, reads useScriptStore itself) ─────────────────────

export function TimelinePanel() {
  const shots = useScriptStore((s) => s.shots);
  const projectId = useScriptStore((s) => s.projectId);
  return (
    <TimelineEditor
      shots={shots}
      projectId={projectId ?? ''}
    />
  );
}
