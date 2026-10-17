import React, { useState, useRef, useEffect } from 'react'
import {
  Send,
  Sparkles,
  Bot,
  User,
  Wrench,
  ChevronDown,
  ChevronRight,
  FileCode,
  GitPullRequest,
  CheckCircle2,
  Trash2,
  RefreshCw,
} from 'lucide-react'
import type { AgentStep, Citation, PatchProposal } from '../types'

interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  steps?: AgentStep[]
  citations?: Citation[]
  proposedPatch?: PatchProposal | null
  timestamp: string
}

interface CopilotChatProps {
  messages: ChatMessageItem[]
  onSendMessage: (text: string) => Promise<void>
  onNavigateCitation: (filePath: string, startLine: number, endLine: number) => void
  onInspectPatch: () => void
  onClearHistory: () => void
  isLoading: boolean
}

export const CopilotChat: React.FC<CopilotChatProps> = ({
  messages,
  onSendMessage,
  onNavigateCitation,
  onInspectPatch,
  onClearHistory,
  isLoading,
}) => {
  const [inputText, setInputText] = useState('')
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({})
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputText.trim() || isLoading) return
    const text = inputText.trim()
    setInputText('')
    await onSendMessage(text)
  }

  const toggleStep = (stepKey: string) => {
    setExpandedSteps((prev) => ({
      ...prev,
      [stepKey]: !prev[stepKey],
    }))
  }

  const quickPrompts = [
    'Investigate zero division in divide_numbers',
    'Where is password hashing handled?',
    'Inspect boundary condition in search_service',
    'Run static analysis on entire codebase',
  ]

  return (
    <aside className="sidebar-assistant">
      <div className="assistant-header">
        <div className="assistant-title">
          <Sparkles size={16} color="#38bdf8" />
          <span>Copilot Assistant</span>
        </div>

        <button
          onClick={onClearHistory}
          style={{ background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer' }}
          title="Clear conversation history"
        >
          <Trash2 size={14} />
        </button>
      </div>

      <div className="chat-history-container">
        {messages.length === 0 ? (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#6e7681',
              gap: '12px',
              padding: '24px',
              textAlign: 'center',
            }}
          >
            <Bot size={36} color="#38bdf8" />
            <div style={{ fontSize: '15px', fontWeight: 600, color: '#f0f6fc' }}>
              How can I help you today?
            </div>
            <p style={{ fontSize: '12px', color: '#8b949e', maxWidth: '300px' }}>
              Ask questions about the repository, investigate failing tests, or request verified patches.
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`message-bubble ${msg.role}`}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '11px',
                  color: '#8b949e',
                  marginBottom: '2px',
                }}
              >
                {msg.role === 'user' ? (
                  <>
                    <User size={12} color="#a855f7" />
                    <span>You</span>
                  </>
                ) : (
                  <>
                    <Bot size={12} color="#38bdf8" />
                    <span>GitContext Copilot</span>
                  </>
                )}
                <span>• {msg.timestamp}</span>
              </div>

              {/* Tool Execution Steps Accordion */}
              {msg.steps && msg.steps.length > 0 && (
                <div style={{ marginBottom: '8px' }}>
                  <div
                    style={{
                      fontSize: '11px',
                      color: '#8b949e',
                      marginBottom: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Wrench size={12} color="#6366f1" />
                    <span>Tool Execution Trace ({msg.steps.length} actions)</span>
                  </div>

                  {msg.steps.map((st, idx) => {
                    const stepKey = `${msg.id}-step-${idx}`
                    const isExpanded = expandedSteps[stepKey]
                    return (
                      <div key={idx} className="tool-step-card">
                        <div className="tool-step-header" onClick={() => toggleStep(stepKey)}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            <span style={{ fontWeight: 600, color: '#38bdf8' }}>
                              {st.action || 'Reasoning'}
                            </span>
                            <span style={{ color: '#8b949e' }}>- {st.thought}</span>
                          </div>
                          <CheckCircle2 size={13} color="#3fb950" />
                        </div>

                        {isExpanded && (
                          <div className="tool-step-body">
                            {st.action_input && (
                              <div style={{ marginBottom: '4px' }}>
                                <strong style={{ color: '#8b949e' }}>Arguments:</strong>{' '}
                                <code>{JSON.stringify(st.action_input)}</code>
                              </div>
                            )}
                            {st.observation && (
                              <div>
                                <strong style={{ color: '#8b949e' }}>Observation:</strong>
                                <pre style={{ marginTop: '2px', whiteSpace: 'pre-wrap' }}>
                                  {JSON.stringify(st.observation, null, 2).slice(0, 500)}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Text content */}
              <div style={{ fontSize: '13px', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                {msg.content}
              </div>

              {/* Embedded Proposed Patch Card */}
              {msg.proposedPatch && (
                <div
                  style={{
                    marginTop: '8px',
                    padding: '10px',
                    background: 'rgba(99, 102, 241, 0.1)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <GitPullRequest size={16} color="#a855f7" />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '12px', color: '#f0f6fc' }}>
                        {msg.proposedPatch.title}
                      </div>
                      <div style={{ fontSize: '11px', color: '#8b949e' }}>
                        Target: {msg.proposedPatch.file_path}
                      </div>
                    </div>
                  </div>
                  <button className="btn-primary" style={{ padding: '4px 10px', fontSize: '11px' }} onClick={onInspectPatch}>
                    Inspect Diff
                  </button>
                </div>
              )}

              {/* Verified Citations List */}
              {msg.citations && msg.citations.length > 0 && (
                <div style={{ marginTop: '8px' }}>
                  <div style={{ fontSize: '11px', color: '#8b949e', marginBottom: '4px' }}>
                    Sources & Verified Citations:
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {msg.citations.map((c, cIdx) => (
                      <button
                        key={cIdx}
                        className="citation-card"
                        onClick={() => onNavigateCitation(c.file_path, c.start_line, c.end_line)}
                        title={`Click to view ${c.file_path} lines L${c.start_line}-L${c.end_line}`}
                      >
                        <FileCode size={12} />
                        <span>
                          [{c.source_index}] {c.file_path}:L{c.start_line}-L{c.end_line}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div
            className="message-bubble assistant"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              color: '#38bdf8',
              fontSize: '13px',
            }}
          >
            <RefreshCw size={15} className="spin" />
            <span>GitContext AI is analyzing repository and running tools...</span>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      <div className="chat-input-area">
        {/* Quick prompt chips */}
        <div className="quick-prompts">
          {quickPrompts.map((p, idx) => (
            <button
              key={idx}
              className="quick-chip"
              onClick={() => onSendMessage(p)}
              disabled={isLoading}
            >
              {p}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="input-box-wrapper">
          <textarea
            placeholder="Ask GitContext a question or command (e.g. 'Investigate zero division')..."
            rows={2}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
          />
          <button
            type="submit"
            className="btn-primary"
            style={{ padding: '8px', borderRadius: '6px' }}
            disabled={isLoading || !inputText.trim()}
          >
            <Send size={15} />
          </button>
        </form>
      </div>
    </aside>
  )
}
