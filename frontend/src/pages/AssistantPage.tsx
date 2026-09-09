import { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, ChevronDown, Circle, FileText, Clock, Shield, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendChat, getConversation } from '../services/api';
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
  const messagesEnd = useRef<HTMLDivElement>(null);

  const handleInputChange = (val: string) => {
    setInput(val);
    setDraftInput?.(val);
  };

  const updateMessages = (newMsgs: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    setMessages(prev => {
      const updated = typeof newMsgs === 'function' ? newMsgs(prev) : newMsgs;
      setDraftMessages?.(updated);
      return updated;
    });
  };

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!activeConversationId) {
      if (draftMessages.length > 0) {
        setMessages(draftMessages);
      }
      return;
    }
    const loadConversation = async () => {
      try {
        const conv = await getConversation(activeConversationId);
        if (conv && conv.messages) {
          const loadedMsgs: ChatMessage[] = conv.messages.map(m => ({
            id: m.id,
            role: m.role,
            content: m.content,
            timestamp: new Date(m.created_at),
            response: m.model ? {
              answer: m.content,
              answer_type: (m.answer_type as any) || 'dataset',
              confidence: m.confidence || 0,
              model: m.model || selectedModel,
              sources: [],
              retrieval: { semantic_results: 0, keyword_results: 0, reranked_results: 0 },
              response_time_ms: 0,
              conversation_id: activeConversationId,
            } : undefined
          }));
          updateMessages(loadedMsgs);
        }
      } catch (err) {
        console.error('Failed to load conversation history:', err);
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
      const errMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: err.response?.data?.detail || err.message || 'An error occurred.',
        timestamp: new Date(),
      };
      updateMessages(prev => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const suggestions = [
    "Summarize the most important information in my dataset",
    "Who teaches DBMS?",
    "Show top 5 students",
    "What class do I have tomorrow?",
  ];

  return (
    <div className="relative flex-1 flex flex-col h-full bg-[#E4E2DD] text-[#1E1E1E] overflow-hidden slide-up">
      {/* Multiply Background Blobs */}
      <div className="absolute -top-20 -left-20 w-96 h-96 rounded-full bg-[#DB4A2B]/20 multiply-blob pointer-events-none" />
      <div className="absolute top-1/3 -right-20 w-96 h-96 rounded-full bg-[#F8A348]/25 multiply-blob pointer-events-none" />
      <div className="absolute -bottom-20 left-1/3 w-96 h-96 rounded-full bg-[#FF89A9]/20 multiply-blob pointer-events-none" />

      {/* Top bar */}
      <div className="relative z-10 flex items-center justify-between px-6 py-4 border-b-2 border-[#1E1E1E] bg-[#E4E2DD]/90 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs font-bold uppercase tracking-widest text-[#DB4A2B] bg-[#1E1E1E] text-white px-2 py-0.5 border border-[#1E1E1E]">POSTER UI</span>
          <h2 className="font-display text-lg font-bold tracking-tight text-[#1E1E1E]">AI Assistant</h2>
        </div>

        {/* Model selector */}
        <div className="relative">
          <button
            onClick={() => setShowModelMenu(!showModelMenu)}
            className="flex items-center gap-2.5 px-3.5 py-1.5 bg-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] hover:shadow-[5px_5px_0px_#1E1E1E] transition-all text-xs font-bold uppercase"
          >
            <Circle className={`w-2.5 h-2.5 fill-current ${currentModel?.available ? 'text-[#DB4A2B]' : 'text-gray-400'}`} />
            <span className="text-[#1E1E1E]">{currentModel?.name || selectedModel}</span>
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
          <EmptyState suggestions={suggestions} onSelect={(s) => { handleInputChange(s); }} />
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {loading && <TypingIndicator model={currentModel?.name || selectedModel} />}
            <div ref={messagesEnd} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="relative z-10 px-6 py-4 border-t-2 border-[#1E1E1E] bg-[#E4E2DD]">
        <div className="max-w-3xl mx-auto">
          <form onSubmit={(e) => { e.preventDefault(); handleSend(); }}
                className="flex gap-3">
            <input
              value={input}
              onChange={e => handleInputChange(e.target.value)}
              placeholder="Ask anything about your dataset..."
              className="input-field flex-1 font-sans font-medium text-sm"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}
                    className="btn-primary px-5" aria-label="Send message">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4 stroke-[3]" />}
            </button>
          </form>
        </div>
      </div>

    </div>
  );
}

/* ── Empty State ─────────────────────────────── */
function EmptyState({ suggestions, onSelect }: { suggestions: string[]; onSelect: (s: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 slide-up">
      <div className="w-20 h-20 bg-[#DB4A2B] border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E]
                      flex items-center justify-center mb-6">
        <Sparkles className="w-10 h-10 text-white" />
      </div>

      <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-[-0.05em] leading-[0.85] text-[#1E1E1E] mb-3 uppercase">
        Knowledge Base
      </h1>
      <h2 className="font-display text-3xl sm:text-4xl font-bold tracking-[-0.05em] leading-[0.85] text-[#DB4A2B] mb-6 uppercase">
        Swiss RAG Intelligence
      </h2>

      <p className="font-sans text-sm font-medium text-[#1E1E1E]/80 max-w-md mb-8 leading-relaxed">
        Upload documents to the Knowledge Base and query your dataset with high precision.
        NEXUS uses hybrid semantic-keyword retrieval grounded by Swiss RAG pipeline.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl">
        {suggestions.map((s, i) => (
          <button key={i} onClick={() => onSelect(s)}
                  className="bg-white border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E]
                             hover:shadow-[6px_6px_0px_#DB4A2B] hover:border-[#1E1E1E]
                             p-4 text-xs font-bold text-[#1E1E1E] text-left transition-all active:translate-x-[1px] active:translate-y-[1px]">
            "{s}"
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Message Bubble ──────────────────────────── */
function MessageBubble({ message }: { message: ChatMessage }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';
  const res = message.response;

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'} slide-up`}>
      <div className={`max-w-[85%] ${isUser ? 'order-1' : ''}`}>
        {/* Content */}
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

        {/* Response metadata */}
        {res && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-mono font-bold">
            <span className={`inline-flex items-center gap-1 border border-[#1E1E1E] px-2 py-0.5
              ${res.answer_type === 'dataset' ? 'bg-[#DB4A2B] text-white'
                : res.answer_type === 'general_knowledge' ? 'bg-[#F8A348] text-[#1E1E1E]'
                : 'bg-[#FF89A9] text-[#1E1E1E]'}`}>
              {res.answer_type === 'dataset' ? 'DATASET' : res.answer_type === 'general_knowledge' ? 'GENERAL' : 'INSUFFICIENT'}
            </span>

            {res.confidence > 0 && (
              <span className="flex items-center gap-1 text-[#1E1E1E]/80 border border-[#1E1E1E] px-1.5 py-0.5 bg-white">
                <Shield className="w-3 h-3 text-[#DB4A2B]" />
                {Math.round(res.confidence * 100)}%
              </span>
            )}

            <span className="flex items-center gap-1 text-[#1E1E1E]/80 border border-[#1E1E1E] px-1.5 py-0.5 bg-white">
              <Clock className="w-3 h-3 text-[#DB4A2B]" />
              {res.response_time_ms} ms
            </span>

            <span className="border border-[#1E1E1E] px-1.5 py-0.5 bg-white uppercase text-[#1E1E1E]">{res.model}</span>

            {res.sources.length > 0 && (
              <button onClick={() => setShowSources(!showSources)}
                      className="flex items-center gap-1 bg-[#1E1E1E] text-white px-2 py-0.5 border border-[#1E1E1E] hover:bg-[#DB4A2B] transition-colors">
                <FileText className="w-3 h-3" />
                {res.sources.length} SOURCE{res.sources.length > 1 ? 'S' : ''}
              </button>
            )}
          </div>
        )}

        {/* Sources panel */}
        {showSources && res?.sources && (
          <div className="mt-2 space-y-1.5">
            {res.sources.map((src, i) => (
              <SourceCard key={i} source={src} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Source Card ──────────────────────────────── */
function SourceCard({ source }: { source: Source }) {
  return (
    <div className="bg-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] p-2.5 text-[10px] font-mono">
      <div className="flex items-center gap-2">
        <FileText className="w-3.5 h-3.5 text-[#DB4A2B] flex-shrink-0" />
        <span className="font-bold text-[#1E1E1E]">{source.file_name}</span>
        <span className="text-[#1E1E1E]/70">
          {source.page ? `Page ${source.page}` : ''}
          {source.section ? ` • ${source.section}` : ''}
          {source.sheet_name ? ` • Sheet: ${source.sheet_name}` : ''}
        </span>
        <span className="ml-auto font-bold text-[#DB4A2B]">{Math.round(source.score * 100)}%</span>
      </div>
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
