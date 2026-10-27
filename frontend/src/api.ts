import type { FormReference, MatchSection, CategoryId } from './types/models';
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '';
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
export type StoredDocument = { id:string; category:CategoryId; subtype?:string; filename:string; size:number; sha256:string; uploaded:number };
export type AnalysisResult = { application_id:string; job_id:string; result_version:string; source:'backend'; form_reference:FormReference; matching_sections:MatchSection[]; errors:Array<{document_id:string;category:CategoryId;filename:string;error:string}>; warnings:string[]; total_documents:number; analyzed_documents:number; finished_at:number; document_fingerprint:[string,string][] };
export type AnalysisJob = {id:string;status:'queued'|'running'|'completed'|'failed';progress:number;message:string;error:string|null};
export async function request<T>(path:string, options:RequestInit={}):Promise<T> {
  const headers = new Headers(options.headers);
  if (authToken) headers.set('Authorization',`Bearer ${authToken}`);
  const response = await fetch(API_BASE + path,{...options,headers,cache:'no-store'});
  if (!response.ok) {
    const body = await response.json().catch(()=>null) as {detail?:string}|null;
    throw new Error(body?.detail || `HTTP ${response.status}: ${response.statusText}`);
  }
  if (response.status===204) return null as T;
  return response.json() as Promise<T>;
}
export function newApplication(){return request<{application_id:string}>('/api/v1/applications',{method:'POST'});}
export function listFiles(aid:string){return request<{documents:StoredDocument[]}>(`/api/v1/applications/${aid}/documents`);}
export function uploadFile(aid:string,category:CategoryId,file:File,subtype?:string){
  const data = new FormData(); data.append('category',category);if(subtype) data.append('subtype',subtype);data.append('file',file);
  return request<{document:StoredDocument}>(`/api/v1/applications/${aid}/documents`,{method:'POST',body:data});
}
export function deleteFile(aid:string,did:string){return request<{deleted:boolean}>(`/api/v1/applications/${aid}/documents/${did}`,{method:'DELETE'});}
export function analyze(aid:string){return request<{job_id:string;status:string;progress:number}>(`/api/v1/applications/${aid}/analyses`,{method:'POST'});}
export function jobStatus(aid:string,jid:string){return request<AnalysisJob>(`/api/v1/applications/${aid}/jobs/${jid}`);}
export function fetchResults(aid:string){return request<AnalysisResult>(`/api/v1/applications/${aid}/results`);}
export async function fetchFile(aid:string,did:string){
  const headers:HeadersInit=authToken?{'Authorization':`Bearer ${authToken}`}:{};
  const r=await fetch(`${API_BASE}/api/v1/applications/${aid}/documents/${did}/file`,{headers,cache:'no-store'});
  if(!r.ok) throw new Error('Dokumen tidak bisa dibuka');
  return await r.blob();
}

export async function fetchPreviewFile(aid:string,did:string){
  const headers:HeadersInit=authToken?{'Authorization':`Bearer ${authToken}`}:{ };
  const r=await fetch(`${API_BASE}/api/v1/applications/${aid}/documents/${did}/preview`,{headers,cache:'no-store'});
  if(!r.ok) throw new Error('Pratinjau bukti tidak dapat ditampilkan');
  return await r.blob();
}

export async function fetchEvidencePage(aid:string,did:string,page:number){
  const headers:HeadersInit=authToken?{'Authorization':`Bearer ${authToken}`}:{ };
  const r=await fetch(`${API_BASE}/api/v1/applications/${aid}/documents/${did}/evidence-page/${page}`,{headers,cache:'no-store'});
  if(!r.ok) throw new Error(`Halaman ${page} tidak bisa ditampilkan`);
  return await r.blob();
}
