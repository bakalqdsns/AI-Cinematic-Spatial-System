// ─────────────────────────────────────────────────────────────────────────────
// AICSS Sequence Player — Compact embeddable frame player
// Simplified playback controls for integration into existing interfaces
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useRef } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { useSequenceStore } from '../../store/useSequenceStore';
import type { FrameResult } from '../../types/sequence';

interface SequencePlayerProps {
  onFrameChange?: (frame: FrameResult) => void;
}

export function SequencePlayer({ onFrameChange }: SequencePlayerProps) {
  const {
    frames,
    currentFrameIndex,
    isPlaying,
    playbackSpeed,
    setCurrentFrame,
    nextFrame,
    prevFrame,
    play,
    pause,
  } = useSequenceStore();

  const intervalRef = useRef<number | null>(null);
  const currentFrame = frames[currentFrameIndex];

  // 通知父组件帧变化
  useEffect(() => {
    if (currentFrame && onFrameChange) {
      onFrameChange(currentFrame);
    }
  }, [currentFrameIndex, currentFrame, onFrameChange]);

  // 播放逻辑
  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = window.setInterval(() => {
        const { currentFrameIndex, frames, nextFrame, pause } = useSequenceStore.getState();
        if (currentFrameIndex >= frames.length - 1) {
          pause();
        } else {
          nextFrame();
        }
      }, 1000 / playbackSpeed);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isPlaying, playbackSpeed]);

  if (frames.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 p-2 bg-gray-900 rounded-lg">
      <button
        onClick={prevFrame}
        disabled={currentFrameIndex === 0}
        className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-30"
      >
        <SkipBack size={16} />
      </button>

      <button
        onClick={isPlaying ? pause : play}
        className="p-1.5 rounded bg-blue-600 hover:bg-blue-500"
      >
        {isPlaying ? <Pause size={18} /> : <Play size={18} />}
      </button>

      <button
        onClick={nextFrame}
        disabled={currentFrameIndex === frames.length - 1}
        className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-30"
      >
        <SkipForward size={16} />
      </button>

      <span className="ml-2 text-xs text-gray-400">
        {currentFrameIndex + 1} / {frames.length}
      </span>

      <div className="ml-4 flex gap-1">
        {frames.map((_, idx) => (
          <button
            key={idx}
            onClick={() => setCurrentFrame(idx)}
            className={`
              w-2 h-2 rounded-full transition-colors
              ${idx === currentFrameIndex ? 'bg-blue-500' : 'bg-gray-600 hover:bg-gray-500'}
            `}
          />
        ))}
      </div>
    </div>
  );
}
