import type { FormReference, MatchSection, CategoryId } from './types/models';
const API_BASE = (() => {
  const envUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');
  if (envUrl) return envUrl;
  const path = window.location.pathname.replace(/\/+$/, '');
  return path || '';
})();
let authToken = (() => {
  try {
    const params = new URLSearchParams(window.location.search);
    const queryToken = params.get('token');
    if (queryToken && queryToken.trim()) {
      return queryToken.trim();
    }
    return localStorage.getItem('bapeten_api_token') || '';
  } catch {
    return '';
  }
})();
export function setApiToken(token: string) { authToken = token.trim(); }
export type StoredDocument = { id: string; category: CategoryId; subtype?: string; filename: string; size: number; sha256: string; uploaded: number };
export type AnalysisResult = { application_id: string; job_id: string; result_version: string; source: 'backend'; form_reference: FormReference; matching_sections: MatchSection[]; errors: Array<{ document_id: string; category: CategoryId; filename: string; error: string }>; warnings: string[]; total_documents: number; analyzed_documents: number; finished_at: number; document_fingerprint: [string, string][] };
export type AnalysisJob = { id: string; status: 'queued' | 'running' | 'completed' | 'failed'; progress: number; message: string; error: string | null };
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`);
  const response = await fetch(API_BASE + path, { ...options, headers, cache: 'no-store' });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(body?.detail || `HTTP ${response.status}: ${response.statusText}`, response.status);
  }
  if (response.status === 204) return null as T;
  return response.json() as Promise<T>;
}
export function newApplication() { return request<{ application_id: string }>('/api/v1/applications', { method: 'POST' }); }
async function monitoringRequest<T>(path: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = window.setTimeout(abort, 15000);
  try { return await request<T>(path, { signal: controller.signal }); }
  finally { window.clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
export function listFiles(aid: string, signal?: AbortSignal) { return monitoringRequest<{ documents: StoredDocument[] }>(`/api/v1/applications/${aid}/documents`, signal); }
export function uploadFile(aid: string, category: CategoryId | string, file: File, subtype?: string) {
  const data = new FormData(); if (category && category !== 'auto') data.append('category', category);
  if (subtype) data.append('subtype', subtype);
  data.append('file', file);
  return request<{ document: StoredDocument }>(`/api/v1/applications/${aid}/documents`, { method: 'POST', body: data });
}
export type ClassifyResponse = {
  filename: string;
  category: CategoryId | 'unknown';
  subtype?: string;
  layer: 1 | 2 | 0;
  reason: string;
  confidence: number;
};
export function classifyFile(file: File) {
  const data = new FormData();
  data.append('file', file);
  return request<ClassifyResponse>('/api/v1/classify', { method: 'POST', body: data });
}
export function deleteFile(aid: string, did: string) { return request<{ deleted: boolean }>(`/api/v1/applications/${aid}/documents/${did}`, { method: 'DELETE' }); }
export function updateFileCategory(aid: string, did: string, category: CategoryId, subtype?: string) {
  return request<{ document: StoredDocument }>(`/api/v1/applications/${aid}/documents/${did}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, subtype: subtype ?? null }),
  });
}
export function analyze(aid: string) { return request<{ job_id: string; status: string; progress: number }>(`/api/v1/applications/${aid}/analyses`, { method: 'POST' }); }
export function jobStatus(aid: string, jid: string, signal?: AbortSignal) { return monitoringRequest<AnalysisJob>(`/api/v1/applications/${aid}/jobs/${jid}`, signal); }
export function latestJob(aid: string, signal?: AbortSignal) { return monitoringRequest<{ job: AnalysisJob | null }>(`/api/v1/applications/${aid}/jobs/latest`, signal); }
export function jobResults(aid: string, jid: string, signal?: AbortSignal) { return monitoringRequest<AnalysisResult>(`/api/v1/applications/${aid}/jobs/${jid}/results`, signal); }
export function fetchResults(aid: string) { return request<AnalysisResult>(`/api/v1/applications/${aid}/results`); }
export async function fetchFile(aid: string, did: string) {
  const headers: HeadersInit = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
  const r = await fetch(`${API_BASE}/api/v1/applications/${aid}/documents/${did}/file`, { headers, cache: 'no-store' });
  if (!r.ok) throw new Error('Dokumen tidak bisa dibuka');
  return await r.blob();
}

export async function fetchPreviewFile(aid: string, did: string) {
  const headers: HeadersInit = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
  const r = await fetch(`${API_BASE}/api/v1/applications/${aid}/documents/${did}/preview`, { headers, cache: 'no-store' });
  if (!r.ok) throw new Error('Pratinjau bukti tidak dapat ditampilkan');
  return await r.blob();
}

export async function fetchEvidencePage(aid: string, did: string, page: number) {
  const headers: HeadersInit = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
  const r = await fetch(`${API_BASE}/api/v1/applications/${aid}/documents/${did}/evidence-page/${page}`, { headers, cache: 'no-store' });
  if (!r.ok) throw new Error(`Halaman ${page} tidak bisa ditampilkan`);
  return await r.blob();
}
