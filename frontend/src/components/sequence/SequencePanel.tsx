// ─────────────────────────────────────────────────────────────────────────────
// AICSS Sequence Panel — Frame management and playback interface
// Displays frame thumbnails, current frame details, cross-frame tracking info
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useRef } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from 'lucide-react';
import { useSequenceStore } from '../../store/useSequenceStore';

export function SequencePanel() {
  const {
    frames,
    currentFrameIndex,
    crossFrameObjects,
    sceneLinks,
    selectedGlobalObjectId,
    isPlaying,
    playbackSpeed,
    loading,
    progress,
    progressMessage,
    error,
    setCurrentFrame,
    nextFrame,
    prevFrame,
    play,
    pause,
    setPlaybackSpeed,
    setSelectedGlobalObjectId,
  } = useSequenceStore();

  const currentFrame = frames[currentFrameIndex];
  const playIntervalRef = useRef<number | null>(null);

  // 播放逻辑
  useEffect(() => {
    if (isPlaying) {
      playIntervalRef.current = window.setInterval(() => {
        const { currentFrameIndex, frames, nextFrame, pause } = useSequenceStore.getState();
        if (currentFrameIndex >= frames.length - 1) {
          pause();
        } else {
          nextFrame();
        }
      }, 1000 / playbackSpeed);
    } else {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current);
        playIntervalRef.current = null;
      }
    }

    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current);
      }
    };
  }, [isPlaying, playbackSpeed]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-4" />
        <p className="text-gray-400">{progressMessage}</p>
        {progress > 0 && progress < 100 && (
          <div className="w-48 h-2 bg-gray-700 rounded-full mt-4 overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8">
        <p className="text-red-400">错误: {error}</p>
      </div>
    );
  }

  if (frames.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-gray-500">
        <p>暂无序列数据</p>
        <p className="text-sm mt-2">请先上传帧序列进行分析</p>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* 帧列表 */}
      <div className="w-48 border-r border-gray-700 overflow-y-auto p-2">
        <h3 className="text-xs text-gray-500 uppercase mb-2 px-2">
          Frames ({frames.length})
        </h3>
        <div className="space-y-1">
          {frames.map((frame, idx) => (
            <button
              key={frame.frameId}
              onClick={() => setCurrentFrame(idx)}
              className={`
                w-full p-2 rounded text-left text-xs transition-colors
                ${idx === currentFrameIndex
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}
              `}
            >
              <div className="font-medium">{frame.frameId}</div>
              <div className="text-gray-500 mt-0.5">
                {frame.frameType || 'unknown'}
              </div>
              <div className="text-gray-600 mt-0.5">
                {frame.objects?.length || 0} objects
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 当前帧详情 */}
      <div className="flex-1 flex flex-col">
        {/* 播放控制 */}
        <div className="flex items-center justify-center gap-2 p-3 border-b border-gray-700">
          <button
            onClick={prevFrame}
            disabled={currentFrameIndex === 0}
            className="p-2 rounded hover:bg-gray-700 disabled:opacity-30"
          >
            <SkipBack size={18} />
          </button>
          <button
            onClick={() => setCurrentFrame(0)}
            disabled={currentFrameIndex === 0}
            className="p-2 rounded hover:bg-gray-700 disabled:opacity-30"
          >
            <ChevronLeft size={18} />
          </button>

          <button
            onClick={isPlaying ? pause : play}
            className="p-2 rounded bg-blue-600 hover:bg-blue-500"
          >
            {isPlaying ? <Pause size={20} /> : <Play size={20} />}
          </button>

          <button
            onClick={() => setCurrentFrame(frames.length - 1)}
            disabled={currentFrameIndex === frames.length - 1}
            className="p-2 rounded hover:bg-gray-700 disabled:opacity-30"
          >
            <ChevronRight size={18} />
          </button>
          <button
            onClick={nextFrame}
            disabled={currentFrameIndex === frames.length - 1}
            className="p-2 rounded hover:bg-gray-700 disabled:opacity-30"
          >
            <SkipForward size={18} />
          </button>

          <select
            value={playbackSpeed}
            onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
            className="ml-4 px-2 py-1 rounded bg-gray-800 text-sm"
          >
            <option value={0.5}>0.5x</option>
            <option value={1}>1x</option>
            <option value={2}>2x</option>
            <option value={4}>4x</option>
          </select>

          <span className="ml-4 text-sm text-gray-500">
            {currentFrameIndex + 1} / {frames.length}
          </span>
        </div>

        {/* 帧信息 */}
        <div className="flex-1 p-4 overflow-y-auto">
          {currentFrame && (
            <div className="space-y-4">
              {/* 帧概览 */}
              <div className="bg-gray-800 rounded-lg p-4">
                <h4 className="text-sm font-medium mb-2">
                  Frame: {currentFrame.frameId}
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                  <div>Type: {currentFrame.frameType || 'N/A'}</div>
                  <div>Objects: {currentFrame.objects?.length || 0}</div>
                  <div>Scene: {currentFrame.vlmScene || 'N/A'}</div>
                  <div>Classes: {currentFrame.vlmClasses?.join(', ') || 'N/A'}</div>
                </div>
              </div>

              {/* 跨帧物体 */}
              {crossFrameObjects.length > 0 && (
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="text-sm font-medium mb-2">
                    Tracked Objects ({crossFrameObjects.length})
                  </h4>
                  <div className="space-y-1">
                    {crossFrameObjects.map((obj) => {
                      const appearsInThisFrame = obj.appearances.some(
                        (a) => a.frameId === currentFrame.frameId
                      );
                      return (
                        <button
                          key={obj.globalId}
                          onClick={() => setSelectedGlobalObjectId(obj.globalId)}
                          className={`
                            w-full px-2 py-1 rounded text-left text-xs transition-colors
                            ${selectedGlobalObjectId === obj.globalId
                              ? 'bg-purple-600 text-white'
                              : appearsInThisFrame
                                ? 'bg-gray-700 text-white'
                                : 'bg-gray-900 text-gray-500'}
                          `}
                        >
                          <span className="font-mono">{obj.globalId.slice(0, 12)}...</span>
                          <span className="ml-2">{obj.classLabel}</span>
                          <span className="ml-2 text-gray-500">
                            ({obj.appearances.length} frames)
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 场景关联 */}
              {sceneLinks.length > 0 && (
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="text-sm font-medium mb-2">
                    Scene Links ({sceneLinks.length})
                  </h4>
                  <div className="space-y-1">
                    {sceneLinks.map((link, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-xs">
                        <span className="text-gray-500">{link.sourceFrameId}</span>
                        <span className="text-gray-600">→</span>
                        <span className="text-gray-500">{link.targetFrameId}</span>
                        <span className="ml-auto px-2 py-0.5 rounded bg-gray-700 text-gray-400">
                          {link.linkType}
                        </span>
                        <span className="text-gray-600">
                          {Math.round(link.confidence * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
