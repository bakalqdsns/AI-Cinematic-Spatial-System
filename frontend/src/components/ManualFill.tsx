import { useState } from 'react';

export function CopyPrompt({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      disabled={!text.trim()}
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setDone(true);
          window.setTimeout(() => setDone(false), 1200);
        });
      }}
      className="px-2 py-1 text-xs rounded bg-gray-800 text-gray-200 disabled:opacity-40"
    >
      {done ? '已复制' : '复制提示词'}
    </button>
  );
}

export function DropSlot({
  label,
  accept,
  busy,
  onFile,
}: {
  label: string;
  accept: string;
  busy?: boolean;
  onFile: (file: File) => void;
}) {
  return (
    <label
      className="flex items-center justify-center min-h-24 border border-dashed border-gray-600 rounded-lg text-sm text-gray-300 cursor-pointer hover:border-blue-400"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const file = event.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = '';
        }}
      />
      {busy ? '正在写入项目…' : label}
    </label>
  );
}
