import React from 'react'
import {
  Bug,
  CheckCircle2,
  ChevronDown,
  Terminal,
  XCircle,
} from 'lucide-react'
import type { BugFinding, TestExecutionSummary } from '../types'

interface InvestigationPanelProps {
  findings: BugFinding[]
  testSummary: TestExecutionSummary | null
  onNavigateCitation: (filePath: string, startLine: number, endLine: number) => void
  isLoading?: boolean
}

export const InvestigationPanel: React.FC<InvestigationPanelProps> = ({
  findings,
  testSummary,
  onNavigateCitation,
  isLoading,
}) => {
  const [expandedTrace, setExpandedTrace] = React.useState<Record<number, boolean>>({})

  const toggleTrace = (idx: number) => {
    setExpandedTrace((prev) => ({
      ...prev,
      [idx]: !prev[idx],
    }))
  }

  if (isLoading) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#8b949e',
        }}
      >
        <span>Running automated bug investigation and test isolation...</span>
      </div>
    )
  }

  if (!findings.length && !testSummary) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#6e7681',
          gap: '12px',
        }}
      >
        <Bug size={42} color="#30363d" />
        <div style={{ fontSize: '15px', fontWeight: 500, color: '#8b949e' }}>
          No Active Bug Investigation
        </div>
        <p style={{ fontSize: '12px', maxWidth: '340px', textAlign: 'center' }}>
          Click "Investigate Defect" in the top bar or ask the Copilot in chat to reproduce and localize issues.
        </p>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Test Execution Summary Box */}
      {testSummary && (
        <div
          style={{
            background: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            padding: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600 }}>
              <Terminal size={16} color="#6366f1" />
              <span>Isolated Test Execution</span>
            </div>
            <div style={{ display: 'flex', gap: '10px', fontSize: '12px' }}>
              <span style={{ color: '#3fb950', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <CheckCircle2 size={13} /> {testSummary.passed_tests} Passed
              </span>
              <span style={{ color: '#f85149', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <XCircle size={13} /> {testSummary.failed_tests} Failed
              </span>
              <span style={{ color: '#8b949e' }}>
                Total: {testSummary.total_tests}
              </span>
            </div>
          </div>

          {/* Failures list */}
          {testSummary.failures && testSummary.failures.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {testSummary.failures.map((fail, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'rgba(248, 81, 73, 0.08)',
                    border: '1px solid rgba(248, 81, 73, 0.3)',
                    borderRadius: '6px',
                    padding: '10px',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <span style={{ fontWeight: 600, color: '#ffa198' }}>{fail.test_name}</span>
                      <span style={{ color: '#f85149', marginLeft: '6px' }}>({fail.error_type})</span>
                      <div style={{ color: '#f0f6fc', marginTop: '2px' }}>{fail.error_message}</div>
                    </div>
                    {fail.suspected_source_file && (
                      <button
                        className="btn-secondary"
                        style={{ padding: '2px 8px', fontSize: '11px' }}
                        onClick={() =>
                          onNavigateCitation(
                            fail.suspected_source_file!,
                            fail.suspected_source_line || 1,
                            (fail.suspected_source_line || 1) + 4
                          )
                        }
                      >
                        Jump to {fail.suspected_source_file}:{fail.suspected_source_line}
                      </button>
                    )}
                  </div>

                  {fail.stack_trace_snippet && (
                    <div style={{ marginTop: '8px' }}>
                      <button
                        onClick={() => toggleTrace(idx)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#8b949e',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '11px',
                        }}
                      >
                        <ChevronDown size={12} />
                        <span>{expandedTrace[idx] ? 'Hide Traceback' : 'Show Traceback'}</span>
                      </button>
                      {expandedTrace[idx] && (
                        <pre
                          style={{
                            marginTop: '6px',
                            background: '#070a0e',
                            padding: '8px',
                            borderRadius: '4px',
                            overflowX: 'auto',
                            fontFamily: 'var(--font-mono)',
                            fontSize: '11px',
                            color: '#e6edf3',
                          }}
                        >
                          {fail.stack_trace_snippet}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Identified Bug Findings */}
      {findings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ fontWeight: 600, fontSize: '14px', color: '#f0f6fc', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Bug size={16} color="#f43f5e" />
            <span>Identified Bug Findings ({findings.length})</span>
          </div>

          {findings.map((f, idx) => (
            <div
              key={idx}
              style={{
                background: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-lg)',
                padding: '14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: '#f0f6fc', fontSize: '13px' }}>
                  [{f.bug_id}] {f.title}
                </span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <span
                    style={{
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 600,
                      background: 'rgba(244, 63, 94, 0.15)',
                      color: '#f43f5e',
                      border: '1px solid rgba(244, 63, 94, 0.3)',
                    }}
                  >
                    {f.severity.toUpperCase()} SEVERITY
                  </span>
                  <span
                    style={{
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 600,
                      background: 'rgba(56, 189, 248, 0.15)',
                      color: '#38bdf8',
                      border: '1px solid rgba(56, 189, 248, 0.3)',
                    }}
                  >
                    {f.confidence.toUpperCase()} CONFIDENCE
                  </span>
                </div>
              </div>

              {/* Location jump */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '12px',
                  color: '#8b949e',
                }}
              >
                <span>Location:</span>
                <button
                  className="citation-card"
                  onClick={() =>
                    onNavigateCitation(
                      f.file_path,
                      f.start_line || f.line || 1,
                      f.end_line || f.line || 1
                    )
                  }
                >
                  <span>
                    {f.file_path}:L{f.start_line || f.line || 1}
                  </span>
                </button>
              </div>

              {/* Root cause */}
              <div style={{ fontSize: '12px', color: '#c9d1d9' }}>
                <strong>Root Cause:</strong> {f.root_cause || f.likely_root_cause || f.description}
              </div>

              {/* Suggested fix */}
              {f.suggested_fix_direction && (
                <div
                  style={{
                    fontSize: '12px',
                    color: '#7ee787',
                    background: 'rgba(46, 160, 67, 0.1)',
                    padding: '6px 10px',
                    borderRadius: '4px',
                    borderLeft: '3px solid #3fb950',
                  }}
                >
                  <strong>Fix Direction:</strong> {f.suggested_fix_direction}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
