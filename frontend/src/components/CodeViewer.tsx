import React, { useEffect, useRef } from 'react'
import { FileCode, Copy, Check } from 'lucide-react'
import type { FileReadResult } from '../types'

interface CodeViewerProps {
  fileData: FileReadResult | null
  highlightRange: [number, number] | null
  isLoading?: boolean
}

export const CodeViewer: React.FC<CodeViewerProps> = ({
  fileData,
  highlightRange,
  isLoading,
}) => {
  const [copied, setCopied] = React.useState(false)
  const lineRefs = useRef<Record<number, HTMLDivElement | null>>({})

  // Auto-scroll to highlighted line range when provided
  useEffect(() => {
    if (highlightRange && highlightRange[0]) {
      const targetLine = highlightRange[0]
      const el = lineRefs.current[targetLine]
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }, [highlightRange, fileData])

  const handleCopy = () => {
    if (!fileData) return
    navigator.clipboard.writeText(fileData.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
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
        <span>Loading source code...</span>
      </div>
    )
  }

  if (!fileData) {
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
        <FileCode size={40} color="#30363d" />
        <div style={{ fontSize: '15px', fontWeight: 500, color: '#8b949e' }}>
          Select a file from the explorer or click a source citation
        </div>
        <p style={{ fontSize: '12px', maxWidth: '320px', textAlign: 'center' }}>
          GitContext will load the file with line numbers, AST symbols, and citation highlights.
        </p>
      </div>
    )
  }

  const isHighlighted = (lineNum: number) => {
    if (!highlightRange) return false
    const [start, end] = highlightRange
    return lineNum >= start && lineNum <= end
  }

  return (
    <div className="code-viewer-container">
      <div className="code-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileCode size={15} color="#38bdf8" />
          <span style={{ fontWeight: 600, color: '#f0f6fc' }}>{fileData.file_path}</span>
          <span
            style={{
              fontSize: '11px',
              padding: '1px 6px',
              borderRadius: '10px',
              background: 'rgba(255, 255, 255, 0.06)',
            }}
          >
            {fileData.total_lines} lines
          </span>
          {highlightRange && (
            <span
              style={{
                fontSize: '11px',
                padding: '1px 8px',
                borderRadius: '10px',
                background: 'rgba(99, 102, 241, 0.2)',
                color: '#38bdf8',
                border: '1px solid rgba(99, 102, 241, 0.4)',
              }}
            >
              Viewing L{highlightRange[0]} - L{highlightRange[1]}
            </span>
          )}
        </div>

        <button
          className="btn-secondary"
          style={{ padding: '4px 8px', fontSize: '11px' }}
          onClick={handleCopy}
        >
          {copied ? <Check size={13} color="#3fb950" /> : <Copy size={13} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      <div className="code-content-wrapper">
        {fileData.lines.map((line) => {
          const highlighted = isHighlighted(line.line_number)
          return (
            <div
              key={line.line_number}
              ref={(el) => {
                lineRefs.current[line.line_number] = el
              }}
              className={`code-line ${highlighted ? 'highlighted' : ''}`}
            >
              <div className="line-number">{line.line_number}</div>
              <div className="line-text">{line.text || ' '}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
