// ─────────────────────────────────────────────────────────────────────────────
// 光照预设 (T13) — 前端镜像 backend/blender/addons/aicss_scene_builder/presets/lighting/*.json
//
// 6 套预设与后端 JSON 一一对应（warm_interior / cool_exterior / dramatic /
// tense_night / soft_morning / misty_grey），便于前端选择的预设名直接作为
// `lightingPreset` 字段写入 shot archive manifest，Blender 端按同名 JSON 还原。
//
// LightSpec 字段与后端 JSON 完全对齐：
//   type:     'SUN' | 'AREA' | 'SPOT'
//   energy:   number  — Blender 能量值，前端按经验缩放为 three.js intensity
//   color:    [r,g,b] — 线性 RGB 0-1
//   location: [x,y,z] — 世界坐标
//   rotation: [x,y,z] — 欧拉角（弧度），three.js 端用于定向灯/聚光灯 target
//   size:     number  — 仅 AREA 用
// ─────────────────────────────────────────────────────────────────────────────

export type LightType = 'SUN' | 'AREA' | 'SPOT';

export interface LightSpec {
  type: LightType;
  energy: number;
  color: [number, number, number];
  location?: [number, number, number];
  rotation?: [number, number, number];
  size?: number;
}

export interface LightingPreset {
  name: string;
  description?: string;
  key: LightSpec;
  fill: LightSpec;
  rim: LightSpec;
}

// ── 6 套预设（与后端 presets/lighting/*.json 同名同字段）──────────────────────

export const LIGHTING_PRESETS: Record<string, LightingPreset> = {
  warm_interior: {
    name: 'Warm Interior',
    description: '温馨室内 — 暖黄主光、中性补光、暖色边缘光',
    key: { type: 'SUN', energy: 3.0, color: [1.0, 0.96, 0.88], location: [8, -8, 12], rotation: [0.6, 0, 0.5] },
    fill: { type: 'AREA', energy: 1.5, color: [0.8, 0.9, 1.0], size: 5, location: [-8, -6, 8], rotation: [0.7, 0, -0.5] },
    rim: { type: 'SPOT', energy: 2.0, color: [1.0, 0.93, 0.8], location: [0, 8, 10], rotation: [-0.7, 0, 0] },
  },
  cool_exterior: {
    name: 'Cool Exterior',
    description: '冷调室外 — 中性白主光、蓝色补光、柔天空边缘光',
    key: { type: 'SUN', energy: 4.0, color: [1.0, 1.0, 1.0], location: [8, -8, 12], rotation: [0.5, 0, 0.4] },
    fill: { type: 'AREA', energy: 1.0, color: [0.6, 0.8, 1.0], size: 6, location: [-8, -6, 8], rotation: [0.6, 0, -0.4] },
    rim: { type: 'SPOT', energy: 1.5, color: [0.9, 0.95, 1.0], location: [0, 8, 10], rotation: [-0.7, 0, 0] },
  },
  dramatic: {
    name: 'Dramatic',
    description: '戏剧高对比 — 聚光主光、暗冷补光、暖色边缘光',
    key: { type: 'SPOT', energy: 6.0, color: [1.0, 0.85, 0.7], location: [6, -6, 10], rotation: [0.7, 0, 0.6] },
    fill: { type: 'AREA', energy: 0.4, color: [0.4, 0.5, 0.7], size: 8, location: [-7, -5, 6], rotation: [0.7, 0, -0.5] },
    rim: { type: 'SPOT', energy: 3.0, color: [1.0, 0.9, 0.6], location: [0, 8, 9], rotation: [-0.7, 0, 0] },
  },
  tense_night: {
    name: 'Tense Night',
    description: '紧张夜场景 — 低能量冷蓝主光 + 高对比暖橙边缘光',
    key: { type: 'SPOT', energy: 2.5, color: [0.55, 0.65, 1.0], location: [6, -6, 9], rotation: [0.6, 0, 0.5] },
    fill: { type: 'AREA', energy: 0.3, color: [0.3, 0.35, 0.5], size: 7, location: [-7, -5, 5], rotation: [0.7, 0, -0.5] },
    rim: { type: 'SPOT', energy: 4.0, color: [1.0, 0.7, 0.4], location: [0, 7, 8], rotation: [-0.7, 0, 0] },
  },
  soft_morning: {
    name: 'Soft Morning',
    description: '柔和晨光 — 低角度暖白主光 + 大面积柔补光',
    key: { type: 'SUN', energy: 2.5, color: [1.0, 0.92, 0.78], location: [10, -10, 6], rotation: [1.0, 0, 0.7] },
    fill: { type: 'AREA', energy: 2.0, color: [0.95, 0.97, 1.0], size: 9, location: [-9, -7, 6], rotation: [0.9, 0, -0.6] },
    rim: { type: 'SPOT', energy: 1.2, color: [1.0, 0.95, 0.85], location: [0, 8, 7], rotation: [-0.8, 0, 0] },
  },
  misty_grey: {
    name: 'Misty Grey',
    description: '雾灰阴天 — 中性灰主光 + 等强度补光，低对比无方向感',
    key: { type: 'AREA', energy: 2.0, color: [0.85, 0.87, 0.9], size: 8, location: [4, -8, 10], rotation: [0.5, 0, 0.3] },
    fill: { type: 'AREA', energy: 2.0, color: [0.8, 0.83, 0.88], size: 10, location: [-6, -6, 8], rotation: [0.6, 0, -0.4] },
    rim: { type: 'AREA', energy: 1.0, color: [0.75, 0.78, 0.82], size: 6, location: [0, 6, 6], rotation: [-0.6, 0, 0] },
  },
};

// ── 场景类型 × 情绪 → 预设名（至少 6 种组合）─────────────────────────────────

export interface MoodOption {
  value: string;
  label: string;
  preset: string;
}

export const MOOD_OPTIONS: MoodOption[] = [
  { value: 'indoor-warm', label: '室内 · 温暖', preset: 'warm_interior' },
  { value: 'outdoor-day', label: '室外 · 白天', preset: 'soft_morning' },
  { value: 'outdoor-night', label: '室外 · 夜晚', preset: 'tense_night' },
  { value: 'tense', label: '紧张 · 戏剧', preset: 'dramatic' },
  { value: 'misty', label: '雾灰 · 阴天', preset: 'misty_grey' },
  { value: 'cold', label: '寒冷 · 冷色', preset: 'cool_exterior' },
];

export const MOOD_TO_PRESET: Record<string, string> = Object.fromEntries(
  MOOD_OPTIONS.map((o) => [o.value, o.preset]),
);

// ── 工具：把后端/前端的 RGB 0-1 转 hex 字符串（供 <input type=color> 用）──────────
export function rgbToHex(rgb: [number, number, number]): string {
  const to = (v: number) => {
    const c = Math.max(0, Math.min(255, Math.round(v * 255)));
    return c.toString(16).padStart(2, '0');
  };
  return `#${to(rgb[0])}${to(rgb[1])}${to(rgb[2])}`;
}

// ── 工具：把 hex 字符串转 RGB 0-1 ─────────────────────────────────────────────
export function hexToRgb(hex: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return [1, 1, 1];
  const n = parseInt(m[1], 16);
  return [(n >> 16 & 0xff) / 255, (n >> 8 & 0xff) / 255, (n & 0xff) / 255];
}

// ── 工具：深拷贝预设（用于编辑本地副本，避免污染 LIGHTING_PRESETS）─────────────
export function clonePreset(p: LightingPreset): LightingPreset {
  return {
    name: p.name,
    description: p.description,
    key: { ...p.key, color: [...p.key.color] as [number, number, number], location: p.key.location ? [...p.key.location] as [number, number, number] : undefined, rotation: p.key.rotation ? [...p.key.rotation] as [number, number, number] : undefined },
    fill: { ...p.fill, color: [...p.fill.color] as [number, number, number], location: p.fill.location ? [...p.fill.location] as [number, number, number] : undefined, rotation: p.fill.rotation ? [...p.fill.rotation] as [number, number, number] : undefined },
    rim: { ...p.rim, color: [...p.rim.color] as [number, number, number], location: p.rim.location ? [...p.rim.location] as [number, number, number] : undefined, rotation: p.rim.rotation ? [...p.rim.rotation] as [number, number, number] : undefined },
  };
}
