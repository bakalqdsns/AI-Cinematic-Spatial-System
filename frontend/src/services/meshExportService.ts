// ─────────────────────────────────────────────────────────────────────────────
// AICSS Mesh Export Service — calls backend mesh export endpoints
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';

const DEFAULT_BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

const client = axios.create({
  baseURL: DEFAULT_BACKEND,
  timeout: 600_000, // 10 minutes for Blender export
});

export interface MeshExportResponse {
  mesh_id: string;
  scope: 'object' | 'layer' | 'scene';
  format: string;
  file_name: string | null;
  file_size: number | null;
  file_sha256: string | null;
  object_count: number;
  vertex_count: number;
  face_count: number;
  include_textures: boolean;
  success: boolean;
  error: string | null;
  blender_available: boolean;
  project_id: string | null;
  download_url: string | null;
}

export interface MeshListItem {
  mesh_id: string;
  scope: string;
  target_id: string;
  format: string;
  file_name: string;
  file_size: number;
  file_sha256: string;
  object_count: number;
  vertex_count: number;
  face_count: number;
  include_textures: boolean;
  created_at: string;
  download_url: string;
}

export interface MeshListResponse {
  meshes: MeshListItem[];
}

export interface BlenderCheckResponse {
  available: boolean;
  path: string | null;
  version: string | null;
  message: string;
  error: string | null;
}

export interface ExportObjectsRequest {
  project_id?: string;
  analysis_result: Record<string, unknown>;
  object_ids?: string[];
  object_assets: Record<string, unknown>;
  billboard_offsets: Record<string, unknown>;
  format: 'glb' | 'fbx';
  include_textures: boolean;
}

export interface ExportLayersRequest {
  project_id?: string;
  layer_assets: Record<string, unknown>;
  format: 'glb' | 'fbx';
  include_textures: boolean;
}

export interface ExportSceneRequest {
  project_id?: string;
  analysis_result: Record<string, unknown>;
  depth_split_result: Record<string, unknown>;
  layer_assets: Record<string, unknown>;
  object_assets: Record<string, unknown>;
  billboard_offsets: Record<string, unknown>;
  format: 'glb' | 'fbx';
  include_textures: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Blender availability check
// ─────────────────────────────────────────────────────────────────────────────

export async function checkBlenderAvailable(): Promise<BlenderCheckResponse> {
  const resp = await client.get<BlenderCheckResponse>('/api/aicss/v2/meshes/check');
  return resp.data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Export functions
// ─────────────────────────────────────────────────────────────────────────────

export async function exportMeshObjects(
  request: ExportObjectsRequest
): Promise<MeshExportResponse> {
  const resp = await client.post<MeshExportResponse>(
    '/api/aicss/v2/meshes/export-objects',
    request
  );
  return resp.data;
}

export async function exportMeshLayers(
  request: ExportLayersRequest
): Promise<MeshExportResponse> {
  const resp = await client.post<MeshExportResponse>(
    '/api/aicss/v2/meshes/export-layers',
    request
  );
  return resp.data;
}

export async function exportMeshScene(
  request: ExportSceneRequest
): Promise<MeshExportResponse> {
  const resp = await client.post<MeshExportResponse>(
    '/api/aicss/v2/meshes/export-scene',
    request
  );
  return resp.data;
}

// ─────────────────────────────────────────────────────────────────────────────
// List and manage exports
// ─────────────────────────────────────────────────────────────────────────────

export async function listMeshExports(
  projectId: string
): Promise<MeshListResponse> {
  const resp = await client.get<MeshListResponse>(
    '/api/aicss/v2/meshes/list',
    { params: { project_id: projectId } }
  );
  return resp.data;
}

export async function getMeshInfo(
  meshId: string,
  projectId: string
): Promise<MeshListItem> {
  const resp = await client.get<MeshListItem>(
    `/api/aicss/v2/meshes/${meshId}/info`,
    { params: { project_id: projectId } }
  );
  return resp.data;
}

export async function deleteMeshExport(
  meshId: string,
  projectId: string
): Promise<void> {
  await client.delete(`/api/aicss/v2/meshes/${meshId}`, {
    params: { project_id: projectId },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Download helpers
// ─────────────────────────────────────────────────────────────────────────────

export function downloadMeshFile(
  meshId: string,
  projectId: string,
  filename?: string
): void {
  const url = `${DEFAULT_BACKEND}/api/aicss/v2/meshes/${meshId}/download?project_id=${encodeURIComponent(projectId)}`;
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || `mesh-${meshId}`;
  link.target = '_blank';
  link.click();
}

export async function downloadMeshBlob(
  meshId: string,
  projectId: string
): Promise<Blob> {
  const url = `${DEFAULT_BACKEND}/api/aicss/v2/meshes/${meshId}/download?project_id=${encodeURIComponent(projectId)}`;
  const resp = await client.get(url, { responseType: 'blob' });
  return resp.data;
}
