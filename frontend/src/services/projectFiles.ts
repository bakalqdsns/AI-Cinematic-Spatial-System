const BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

export function projectFileUrl(projectId: string, rel: string): string {
  return `${BACKEND}/api/aicss/v2/projects/${encodeURIComponent(projectId)}/file?rel=${encodeURIComponent(rel)}`;
}

export function imageSrc(projectId: string | null, value?: string): string {
  if (!value) return '';
  if (value.startsWith('data:') || value.startsWith('blob:')) return value;
  if (value.startsWith('http://') || value.startsWith('https://') || value.startsWith('/api/')) return value;
  const windowsAbs = /^[A-Za-z]:[\\/]/.test(value);
  if (!windowsAbs && !value.startsWith('/') && (value.includes('/') || value.includes('\\'))) {
    return projectId ? projectFileUrl(projectId, value) : '';
  }
  if (!value.includes('/') && !value.includes('\\') && value.length > 200) {
    return `data:image/png;base64,${value}`;
  }
  if (windowsAbs || value.startsWith('/')) {
    return `${BACKEND}/api/aicss/v2/media?path=${encodeURIComponent(value)}`;
  }
  return projectId ? projectFileUrl(projectId, value) : '';
}
