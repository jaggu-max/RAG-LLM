/* TypeScript interfaces matching backend schemas */

export interface ChatRequest {
  message: string;
  model: string;
  conversation_id?: string;
  use_knowledge_base: boolean;
}

export interface Source {
  file_name: string;
  document_id?: string;
  file_type?: string;
  page?: number;
  pages?: number[];
  slide_number?: number;
  slides?: number[];
  section?: string;
  chunk_id?: string;
  chunk_count?: number;
  score: number;
  sheet_name?: string;
}

export interface RetrievalInfo {
  semantic_results: number;
  keyword_results: number;
  reranked_results: number;
  unique_source_count?: number;
}

export interface ChatResponse {
  answer: string;
  answer_type: 'dataset' | 'general_knowledge' | 'insufficient';
  confidence: number;
  model: string;
  sources: Source[];
  retrieval: RetrievalInfo;
  response_time_ms: number;
  conversation_id?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: ChatResponse;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  answer_type?: string;
  confidence?: number;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: ConversationMessage[];
}

export interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  chunks: number;
  status: 'pending' | 'processing' | 'indexed' | 'failed';
  indexed_at?: string;
  updated_at?: string;
  file_hash: string;
}

export interface DocumentListResponse {
  documents: DocumentItem[];
  total: number;
}

export interface HealthStatus {
  backend: string;
  chromadb: string;
  embeddings: string;
  gemini: string;
  lmstudio: string;
  watcher: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  available: boolean;
}

export interface ModelsResponse {
  models: ModelInfo[];
}

export interface DocsByType {
  file_type: string;
  count: number;
}

export interface StatsData {
  total_documents: number;
  indexed_documents: number;
  pending_documents: number;
  failed_documents: number;
  total_chunks: number;
  dataset_size_bytes: number;
  total_queries: number;
  avg_response_time_ms: number;
  avg_confidence: number;
  documents_by_type: DocsByType[];
}
