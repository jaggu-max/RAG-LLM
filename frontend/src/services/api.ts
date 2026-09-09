/* API service — Axios client for backend communication */

import axios from 'axios';
import type {
  ChatRequest, ChatResponse, DocumentListResponse, DocumentItem,
  HealthStatus, ModelsResponse, StatsData, Conversation,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Chat ────────────────────────────────────────
export const sendChat = async (req: ChatRequest): Promise<ChatResponse> => {
  const { data } = await api.post<ChatResponse>('/chat', req);
  return data;
};

export const streamChat = (req: ChatRequest): EventSource | null => {
  // Use fetch for SSE since axios doesn't support it natively
  return null; // We'll use fetch-based streaming in the hook
};

// ── Documents ───────────────────────────────────
export const getDocuments = async (): Promise<DocumentListResponse> => {
  const { data } = await api.get<DocumentListResponse>('/documents');
  return data;
};

export const getDocument = async (id: string): Promise<DocumentItem> => {
  const { data } = await api.get<DocumentItem>(`/documents/${id}`);
  return data;
};

export const uploadDocument = async (
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ message: string; document_id: string; filename: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress?.(percent);
      }
    },
  });
  return data;
};

export const deleteDocument = async (id: string): Promise<void> => {
  await api.delete(`/documents/${id}`);
};

export const reindexDocument = async (id: string): Promise<void> => {
  await api.post(`/documents/${id}/reindex`);
};

export const reindexAll = async (): Promise<{ message: string; documents_processed: number }> => {
  const { data } = await api.post('/reindex');
  return data;
};

// ── Health ──────────────────────────────────────
export const getHealth = async (): Promise<HealthStatus> => {
  const { data } = await api.get<HealthStatus>('/health');
  return data;
};

// ── Models ──────────────────────────────────────
export const getModels = async (): Promise<ModelsResponse> => {
  const { data } = await api.get<ModelsResponse>('/models');
  return data;
};

export const testGeminiKey = async (apiKey?: string): Promise<{ status: string; message: string; valid: boolean }> => {
  const { data } = await api.post('/models/test-gemini-key', { api_key: apiKey });
  return data;
};

export const saveGeminiKey = async (apiKey: string): Promise<{ status: string; message: string; valid: boolean }> => {
  const { data } = await api.post('/models/save-gemini-key', { api_key: apiKey });
  return data;
};


// ── Stats ───────────────────────────────────────
export const getStats = async (): Promise<StatsData> => {
  const { data } = await api.get<StatsData>('/stats');
  return data;
};

// ── Conversations ────────────────────────────────
export const getConversations = async (): Promise<{ conversations: Conversation[] }> => {
  const { data } = await api.get<{ conversations: Conversation[] }>('/conversations');
  return data;
};

export const createConversation = async (title: string = 'New Conversation'): Promise<Conversation> => {
  const { data } = await api.post<Conversation>('/conversations', { title });
  return data;
};

export const getConversation = async (id: string): Promise<Conversation> => {
  const { data } = await api.get<Conversation>(`/conversations/${id}`);
  return data;
};

export const deleteConversation = async (id: string): Promise<{ status: string; id: string }> => {
  const { data } = await api.delete<{ status: string; id: string }>(`/conversations/${id}`);
  return data;
};

export { API_BASE };
export default api;
