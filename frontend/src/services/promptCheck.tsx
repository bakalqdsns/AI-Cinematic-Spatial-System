/** 与 backend/app/services/prompt_contract.py 的本地检查保持一致。 */

function low(text: string): string {
  return (text || '').toLowerCase();
}

function hasExactCount(text: string): boolean {
  return /\bexactly\s+(one|two|three|four|\d+)\b/i.test(text);
}

function hasSpecificLight(text: string): boolean {
  const value = low(text);
  const sources = ['sun', 'lamp', 'window', 'key light', 'moon', 'neon', 'firelight', 'bulb', 'skylight', 'daylight', 'moonlight', 'practical'];
  const directions = ['from the', 'from screen', 'from above', 'from behind', 'from camera', 'screen-left', 'screen-right', 'front-left', 'front-right', 'camera-left', 'camera-right'];
  return sources.some((word) => value.includes(word)) && directions.some((word) => value.includes(word));
}

function styleIssues(text: string): string[] {
  const value = low(text);
  if (['paper-craft', 'papercraft', 'cardboard', 'craft-paper', 'anime art'].some((word) => value.includes(word))) {
    return ['出现了不该默认的纸艺或动漫风格'];
  }
  return [];
}

const CAMERA_FAMILIES: Record<string, string[]> = {
  dolly: ['dolly', 'push in', 'push-in', 'pull out', 'pull-out'],
  pan: ['pan ', 'pan left', 'pan right'],
  tilt: ['tilt'],
  zoom: ['zoom'],
  crane: ['crane'],
  orbit: ['orbit'],
  track: ['tracking', 'track left', 'track right'],
  handheld: ['handheld'],
};

function cameraFamilies(text: string): string[] {
  const value = low(text);
  return Object.entries(CAMERA_FAMILIES)
    .filter(([, keys]) => keys.some((key) => value.includes(key)))
    .map(([name]) => name);
}

export function checkCharacterPrompt(text: string): string[] {
  const value = low(text);
  const issues: string[] = [];
  if (!hasExactCount(text)) issues.push('没有写明画面里恰好有几个人');
  if (!['face', 'hair', 'build', 'shoulder'].some((word) => value.includes(word))) {
    issues.push('没有写下能认出同一个人的身份');
  }
  if (!['wear', 'wearing', 'clothes', 'clothing', 'dressed', 'coat', 'shirt', 'dress', 'jacket', 'uniform'].some((word) => value.includes(word))) {
    issues.push('没有写当前服装');
  }
  if (!['front view', 'facing the camera', 'facing camera', 'looks at the camera', 'looking at the camera'].some((word) => value.includes(word))) {
    issues.push('没有写成正面、看向镜头');
  }
  if (!['plain background', 'simple background', 'solid background', 'neutral background'].some((word) => value.includes(word))) {
    issues.push('没有写成简单背景');
  }
  if (!hasSpecificLight(text)) issues.push('光源不够具体');
  return issues.concat(styleIssues(text));
}

export function checkScenePrompt(text: string): string[] {
  const value = low(text);
  const issues: string[] = [];
  if (!['no people', 'no person', 'nobody', 'empty of people'].some((word) => value.includes(word))) {
    issues.push('没有声明场景里没有人');
  }
  if (!value.includes('foreground') || !value.includes('background') || (!value.includes('midground') && !value.includes('mid-ground'))) {
    issues.push('没有写全前景、中景和背景');
  }
  if (!hasSpecificLight(text)) issues.push('光源不够具体');
  if (!text.includes('16:9') && !value.includes('widescreen')) issues.push('没有写成 16:9 全景');
  return issues.concat(styleIssues(text));
}

export function checkActionPrompt(text: string): string[] {
  const value = low(text);
  const issues: string[] = [];
  if (!hasExactCount(text)) issues.push('没有写明画面里恰好有几个人');
  if (!['open:', 'open state', 'first frame', 'starting pose'].some((word) => value.includes(word))) {
    issues.push('没有写起始姿态');
  }
  if (!['close:', 'final frame', 'end state', 'ending pose'].some((word) => value.includes(word))) {
    issues.push('没有写结束姿态');
  }
  const families = cameraFamilies(text);
  if (families.length > 1) issues.push('同时写了不止一种运镜');
  else if (families.length === 0 && !value.includes('static') && !value.includes('camera')) {
    issues.push('没有写运镜的起点和终点');
  }
  return issues;
}

export function checkV2vPrompt(text: string): string[] {
  const issues: string[] = [];
  if (!text.includes('必须保持')) issues.push('没有写必须保持的部分');
  if (!text.includes('只允许改变')) issues.push('没有写只允许改变的部分');
  if (!text.includes('参考视频是本条渲染结果')) issues.push('没有写参考视频是本条渲染结果');
  if (text.includes('（还没有填写）')) issues.push('还没有写允许改变的那一句');
  return issues;
}

export function buildV2vPrompt(sentence: string): string {
  const change = sentence.trim() || '（还没有填写）';
  return [
    '必须保持：已渲染的场景分层、机位和这条分镜已有的动作。未写到的身份、空间和时长保持不变。',
    `只允许改变：${change}`,
    '参考视频是本条渲染结果。',
  ].join('\n');
}

export function PromptIssueList({ issues }: { issues: string[] }) {
  if (issues.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5 text-xs text-amber-300">
      {issues.map((issue) => <li key={issue}>{issue}</li>)}
    </ul>
  );
}
