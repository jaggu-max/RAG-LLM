import { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, ChevronDown, Circle, FileText, Loader2, ExternalLink, Terminal, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendChat, getConversation } from '../services/api';
import DocumentViewerModal from '../components/DocumentViewerModal';
import type { ChatMessage, ChatResponse, ModelInfo, Source } from '../types';

interface Props {
  models: ModelInfo[];
  selectedModel: string;
  onModelChange: (m: string) => void;
  activeConversationId?: string | null;
  setActiveConversationId?: (id: string | null) => void;
  onConversationUpdated?: () => void;
  draftInput?: string;
  setDraftInput?: (val: string) => void;
  draftMessages?: ChatMessage[];
  setDraftMessages?: (msgs: ChatMessage[]) => void;
}

export default function AssistantPage({
  models,
  selectedModel,
  onModelChange,
  activeConversationId,
  setActiveConversationId,
  onConversationUpdated,
  draftInput = '',
  setDraftInput,
  draftMessages = [],
  setDraftMessages,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(draftMessages);
  const [input, setInput] = useState(draftInput);
  const [loading, setLoading] = useState(false);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [activeViewerDoc, setActiveViewerDoc] = useState<{
    id: string;
    filename: string;
    file_type: string;
    size_bytes: number;
    chunks_count: number;
    status: string;
    full_text: string;
    chunks: Array<{ chunk_id: string; text: string }>;
    initialSlide?: number;
    highlightText?: string;
  } | null>(null);

  const messagesEnd = useRef<HTMLDivElement>(null);

  const handleInputChange = (val: string) => {
    setInput(val);
    setDraftInput?.(val);
  };

  const updateMessages = (newMsgs: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    setMessages(newMsgs);
  };

  useEffect(() => {
    setDraftMessages?.(messages);
  }, [messages]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!activeConversationId) {
      if (draftMessages.length > 0 && messages.length === 0) {
        setMessages(draftMessages);
      }
      return;
    }

    const loadConversation = async () => {
      try {
        const conv = await getConversation(activeConversationId);
        if (conv && conv.messages) {
          const loadedMsgs: ChatMessage[] = conv.messages.map(m => {
            const rawSources = (m as any).sources;
            let parsedSources: any[] = [];
            if (rawSources) {
              try {
                parsedSources = typeof rawSources === 'string' ? JSON.parse(rawSources) : rawSources;
              } catch (e) {
                parsedSources = [];
              }
            }
            return {
              id: m.id,
              role: m.role as 'user' | 'assistant',
              content: m.content,
              timestamp: new Date(m.created_at),
              response: m.model ? {
                answer: m.content,
                answer_type: (m.answer_type as any) || 'dataset',
                confidence: m.confidence || 0,
                model: m.model || selectedModel,
                sources: Array.isArray(parsedSources) ? parsedSources : [],
                retrieval: { semantic_results: 0, keyword_results: 0, reranked_results: 0, unique_source_count: Array.isArray(parsedSources) ? parsedSources.length : 0 },
                response_time_ms: 0,
                conversation_id: activeConversationId,
              } : undefined
            };
          });
          setMessages(loadedMsgs);
        }
      } catch (err) {
        console.warn('Conversation not found or deleted:', activeConversationId);
      }
    };

    loadConversation();
  }, [activeConversationId]);

  const currentModel = models.find(m => m.id === selectedModel);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    handleInputChange('');

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    updateMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const res: ChatResponse = await sendChat({
        message: text,
        model: selectedModel,
        conversation_id: activeConversationId || undefined,
        use_knowledge_base: true,
      });

      if (res.conversation_id && res.conversation_id !== activeConversationId) {
        setActiveConversationId?.(res.conversation_id);
      }
      onConversationUpdated?.();

      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.answer,
        timestamp: new Date(),
        response: res,
      };
      updateMessages(prev => [...prev, aiMsg]);
    } catch (err: any) {
      const errText = err.response?.data?.detail || err.message || 'An error occurred.';
      const errMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: errText,
        timestamp: new Date(),
      };
      updateMessages(prev => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenSourceViewer = (src: Source) => {
    const fileExt = src.file_name.split('.').pop()?.toLowerCase() || 'pdf';
    const targetSlide = (src.slides && src.slides.length > 0) ? src.slides[0] : ((src.pages && src.pages.length > 0) ? src.pages[0] : (src.slide_number || src.page || 1));

    setActiveViewerDoc({
      id: src.document_id || src.file_name,
      filename: src.file_name,
      file_type: src.file_type || fileExt,
      size_bytes: 0,
      chunks_count: src.chunk_count || 1,
      status: 'indexed',
      full_text: '',
      chunks: [],
      initialSlide: targetSlide,
      highlightText: src.snippet,
    });
  };

  return (
    <div className="relative flex-1 flex flex-col h-full bg-[#E4E2DD] text-[#1E1E1E] overflow-hidden slide-up">
      {/* Background Blobs */}
      <div className="absolute -top-20 -left-20 w-96 h-96 rounded-full bg-[#DB4A2B]/20 multiply-blob pointer-events-none" />
      <div className="absolute top-1/3 -right-20 w-96 h-96 rounded-full bg-[#F8A348]/25 multiply-blob pointer-events-none" />
      <div className="absolute -bottom-20 left-1/3 w-96 h-96 rounded-full bg-[#FF89A9]/20 multiply-blob pointer-events-none" />

      {/* Top bar */}
      <div className="relative z-10 flex items-center justify-between px-6 py-4 border-b-2 border-[#1E1E1E] bg-[#E4E2DD]/90 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs font-bold uppercase tracking-widest text-[#DB4A2B] bg-[#1E1E1E] text-white px-2 py-0.5 border border-[#1E1E1E]">MASTER RAG</span>
          <h2 className="font-display text-lg font-bold tracking-tight text-[#1E1E1E]">Enterprise Assistant</h2>
        </div>

        {/* Model selector */}
        <div className="relative">
          <button
            onClick={() => setShowModelMenu(!showModelMenu)}
            className="flex items-center gap-2.5 px-3.5 py-1.5 bg-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] hover:shadow-[5px_5px_0px_#1E1E1E] transition-all text-xs font-bold uppercase"
          >
            <Circle className={`w-2.5 h-2.5 fill-current ${currentModel?.available !== false ? 'text-[#DB4A2B]' : 'text-gray-400'}`} />
            <span className="text-[#1E1E1E]">{currentModel?.name || (selectedModel === 'local_qwen' ? 'Ollama (gemma3:4b)' : selectedModel)}</span>
            <ChevronDown className="w-3.5 h-3.5 text-[#1E1E1E]" />
          </button>

          {showModelMenu && (
            <div className="absolute right-0 mt-2 w-56 bg-white border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E] z-50 py-1">
              {models.map(m => (
                <button
                  key={m.id}
                  onClick={() => { onModelChange(m.id); setShowModelMenu(false); }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 text-xs text-left font-bold uppercase transition-colors
                    ${m.id === selectedModel ? 'bg-[#DB4A2B] text-white' : 'text-[#1E1E1E] hover:bg-[#E4E2DD]'}`}
                >
                  <Circle className={`w-2 h-2 fill-current flex-shrink-0 ${m.available ? 'text-emerald-400' : 'text-gray-400'}`} />
                  <div className="flex-1">
                    <p className="font-bold">{m.name}</p>
                    <p className="font-mono text-[9px] opacity-80 mt-0.5">
                      {m.provider === 'lmstudio' ? 'LOCAL ONLY' : (m.available ? 'READY' : 'OFFLINE')}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div className="relative z-10 flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map(msg => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onOpenSource={handleOpenSourceViewer}
              />
            ))}
            {loading && <TypingIndicator model={currentModel?.name || selectedModel} />}
            <div ref={messagesEnd} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="relative z-10 px-6 py-4 border-t-2 border-[#1E1E1E] bg-[#E4E2DD]">
        <div className="max-w-3xl mx-auto">
          <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="flex gap-3">
            <input
              value={input}
              onChange={e => handleInputChange(e.target.value)}
              placeholder="Ask anything about your uploaded knowledge base..."
              className="input-field flex-1 font-sans font-medium text-sm"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()} className="btn-primary px-5" aria-label="Send message">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4 stroke-[3]" />}
            </button>
          </form>
        </div>
      </div>

      {/* Document Viewer Modal */}
      {activeViewerDoc && (
        <DocumentViewerModal
          doc={activeViewerDoc}
          onClose={() => setActiveViewerDoc(null)}
          initialSlide={activeViewerDoc.initialSlide}
          highlightText={activeViewerDoc.highlightText}
        />
      )}
    </div>
  );
}

/* ── Minimalist Clean Empty State (No Sample Cards) ──── */
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 slide-up py-16">
      <div className="w-16 h-16 bg-[#DB4A2B] border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E] flex items-center justify-center mb-6">
        <Sparkles className="w-8 h-8 text-white" />
      </div>

      <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight text-[#1E1E1E] mb-2 uppercase">
        NEXUS RAG
      </h1>
      <h2 className="font-mono text-xs font-bold tracking-widest text-[#DB4A2B] uppercase mb-6 bg-[#1E1E1E] text-white px-3 py-1 border border-[#1E1E1E]">
        DOCUMENT INTELLIGENCE ASSISTANT
      </h2>

      <p className="font-sans text-sm font-medium text-[#1E1E1E]/80 max-w-md leading-relaxed">
        Ask precise questions about your uploaded documents. NEXUS retrieves factual evidence using multi-strategy hybrid search and local LLM reasoning.
      </p>
    </div>
  );
}

/* ── Message Bubble ──────────────────────────── */
function MessageBubble({
  message,
  onOpenSource,
}: {
  message: ChatMessage;
  onOpenSource: (src: Source) => void;
}) {
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showSourcesPop, setShowSourcesPop] = useState(false);
  const isUser = message.role === 'user';
  const res = message.response;

  // Deduplicate sources by document_id or file_name if present
  const uniqueSources: Source[] = [];
  if (res && res.sources && res.sources.length > 0) {
    const seen = new Set<string>();
    for (const src of res.sources) {
      const key = src.document_id || src.file_name;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueSources.push(src);
      }
    }
  }

  const uniqueSourceCount = res?.retrieval?.unique_source_count || uniqueSources.length;

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'} slide-up`}>
      <div className={`max-w-[85%] ${isUser ? 'order-1' : ''}`}>
        {/* Answer Content */}
        <div className={`border-2 border-[#1E1E1E] p-4 text-sm leading-relaxed
          ${isUser
            ? 'bg-[#1E1E1E] text-[#E4E2DD] shadow-[4px_4px_0px_#DB4A2B]'
            : 'bg-white text-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E]'
          }`}>
          {isUser ? (
            <p className="font-medium">{message.content}</p>
          ) : (
            <div className="chat-markdown">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Compact Sources Trigger & Popover */}
        {!isUser && uniqueSources.length > 0 && (
          <div className="relative mt-2">
            <button
              onClick={() => setShowSourcesPop(!showSourcesPop)}
              className="inline-flex items-center gap-1.5 font-mono text-xs font-bold bg-white text-[#1E1E1E] hover:bg-[#DB4A2B] hover:text-white border-2 border-[#1E1E1E] shadow-[2px_2px_0px_#1E1E1E] px-2.5 py-1 transition-all"
            >
              <FileText className="w-3.5 h-3.5 text-[#DB4A2B]" />
              <span>{uniqueSourceCount} {uniqueSourceCount === 1 ? 'SOURCE' : 'SOURCES'}</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showSourcesPop ? 'rotate-180' : ''}`} />
            </button>

            {/* Compact Source Popover Card */}
            {showSourcesPop && (
              <div className="absolute left-0 mt-2 w-80 sm:w-96 bg-white border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E] z-40 p-3 space-y-2 slide-up">
                <div className="flex items-center justify-between border-b border-[#1E1E1E]/20 pb-1.5 mb-2">
                  <span className="font-mono text-[10px] font-bold text-[#DB4A2B] uppercase">CITED SOURCES ({uniqueSourceCount})</span>
                  <button onClick={() => setShowSourcesPop(false)} className="text-gray-400 hover:text-[#1E1E1E]">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                {uniqueSources.map((src, i) => (
                  <CompactSourceCard key={i} source={src} onOpen={() => onOpenSource(src)} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Developer Diagnostics Toggle & Panel */}
        {!isUser && res && (
          <div className="mt-2">
            <button
              onClick={() => setShowDiagnostics(!showDiagnostics)}
              className="flex items-center gap-1.5 font-mono text-[10px] font-bold text-gray-600 hover:text-[#1E1E1E] bg-white/70 border border-[#1E1E1E]/30 px-2 py-0.5 transition-colors"
            >
              <Terminal className="w-3 h-3 text-[#DB4A2B]" />
              {showDiagnostics ? 'HIDE DEVELOPER DIAGNOSTICS' : 'DEVELOPER DIAGNOSTICS'}
            </button>

            {showDiagnostics && (
              <div className="mt-1.5 p-3 bg-[#1E1E1E] text-white border border-[#1E1E1E] font-mono text-[10px] space-y-1 slide-up">
                <div className="flex justify-between border-b border-white/20 pb-1 mb-1">
                  <span className="text-white/60">MODEL:</span>
                  <span className="font-bold text-[#F8A348]">{res.model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/60">RESPONSE TIME:</span>
                  <span>{res.response_time_ms} ms</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/60">ANSWER TYPE:</span>
                  <span className="uppercase text-[#DB4A2B] font-bold">{res.answer_type}</span>
                </div>
                {res.retrieval && (
                  <div className="flex justify-between">
                    <span className="text-white/60">CHUNKS (SEM/KEY/RERANK):</span>
                    <span>{res.retrieval.semantic_results} / {res.retrieval.keyword_results} / {res.retrieval.reranked_results}</span>
                  </div>
                )}
                {res.confidence > 0 && (
                  <div className="flex justify-between">
                    <span className="text-white/60">INTERNAL DENSE SCORE:</span>
                    <span>{(res.confidence * 100).toFixed(1)}%</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Compact Source Card Component ────────────── */
function CompactSourceCard({ source, onOpen }: { source: Source; onOpen: () => void }) {
  const slidesStr = source.slides && source.slides.length > 0
    ? `Slides: ${source.slides.join(', ')}`
    : (source.slide_number ? `Slide ${source.slide_number}` : '');

  const pagesStr = source.pages && source.pages.length > 0
    ? `Pages: ${source.pages.join(', ')}`
    : (source.page ? `Page ${source.page}` : '');

  const locationInfo = slidesStr || pagesStr || (source.section ? `Section: ${source.section}` : '');

  return (
    <div className="bg-[#F9F8F5] border border-[#1E1E1E] p-2.5 space-y-1.5 shadow-[2px_2px_0px_#1E1E1E]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 overflow-hidden pr-2">
          <FileText className="w-3.5 h-3.5 text-[#DB4A2B] flex-shrink-0" />
          <p className="font-mono text-xs font-bold text-[#1E1E1E] truncate">{source.file_name}</p>
        </div>
        <button
          onClick={onOpen}
          className="flex items-center gap-1 bg-[#1E1E1E] text-white hover:bg-[#DB4A2B] text-[10px] font-mono font-bold px-2 py-0.5 transition-colors flex-shrink-0"
        >
          <span>Open Source</span>
          <ExternalLink className="w-2.5 h-2.5" />
        </button>
      </div>

      {locationInfo && (
        <p className="font-mono text-[10px] text-[#DB4A2B] font-bold">{locationInfo}</p>
      )}

      {source.snippet && (
        <p className="font-mono text-[10px] text-gray-700 bg-white p-1.5 border border-[#1E1E1E]/20 line-clamp-2 leading-tight">
          "{source.snippet}"
        </p>
      )}
    </div>
  );
}

/* ── Typing Indicator ────────────────────────── */
function TypingIndicator({ model }: { model: string }) {
  return (
    <div className="flex gap-3 slide-up">
      <div className="bg-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <div className="w-2 h-2 bg-[#DB4A2B] typing-dot" />
            <div className="w-2 h-2 bg-[#DB4A2B] typing-dot" />
            <div className="w-2 h-2 bg-[#DB4A2B] typing-dot" />
          </div>
          <span className="font-mono text-[10px] font-bold text-[#1E1E1E] uppercase">{model} is reasoning...</span>
        </div>
      </div>
    </div>
  );
}
