import React, { useState } from 'react'
import {
  GitPullRequest,
  Check,
  X,
  Play,
  RotateCcw,
  ShieldCheck,
  AlertTriangle,
  FileDiff,
} from 'lucide-react'
import type { PatchProposal } from '../types'

interface DiffViewerProps {
  patch: PatchProposal | null
  onApplyPatch: (patchId: string) => Promise<void>
  onRejectPatch: (patchId: string) => Promise<void>
  onVerifyPatch: (patchId: string) => Promise<void>
  onRollbackPatch: (patchId: string) => Promise<void>
  isLoading?: boolean
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  patch,
  onApplyPatch,
  onRejectPatch,
  onVerifyPatch,
  onRollbackPatch,
  isLoading,
}) => {
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  if (!patch) {
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
        <FileDiff size={42} color="#30363d" />
        <div style={{ fontSize: '15px', fontWeight: 500, color: '#8b949e' }}>
          No Proposed Code Changes
        </div>
        <p style={{ fontSize: '12px', maxWidth: '340px', textAlign: 'center' }}>
          When the AI agent diagnoses an issue or you ask for a refactor, proposed patches will appear here as unified diffs for review before applying.
        </p>
      </div>
    )
  }

  const getStatusBadge = () => {
    switch (patch.status) {
      case 'verified':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              background: 'rgba(46, 160, 67, 0.2)',
              color: '#3fb950',
              border: '1px solid rgba(46, 160, 67, 0.4)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <ShieldCheck size={13} /> VERIFIED BY TESTS
          </span>
        )
      case 'applied':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              background: 'rgba(56, 189, 248, 0.2)',
              color: '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.4)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <Check size={13} /> APPLIED TO DISK
          </span>
        )
      case 'rejected':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              background: 'rgba(248, 81, 73, 0.2)',
              color: '#f85149',
              border: '1px solid rgba(248, 81, 73, 0.4)',
            }}
          >
            REJECTED
          </span>
        )
      case 'reverted':
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              background: 'rgba(210, 153, 34, 0.2)',
              color: '#d29922',
              border: '1px solid rgba(210, 153, 34, 0.4)',
            }}
          >
            REVERTED
          </span>
        )
      default:
        return (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              background: 'rgba(99, 102, 241, 0.2)',
              color: '#a855f7',
              border: '1px solid rgba(99, 102, 241, 0.4)',
            }}
          >
            PENDING REVIEW
          </span>
        )
    }
  }

  const renderDiffLines = () => {
    const rawLines = patch.diff.split('\n')
    return rawLines.map((line, idx) => {
      let lineType = 'context'
      if (line.startsWith('+') && !line.startsWith('+++')) lineType = 'add'
      else if (line.startsWith('-') && !line.startsWith('---')) lineType = 'del'
      else if (line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')) lineType = 'header'

      return (
        <div key={idx} className={`diff-line ${lineType}`}>
          <span style={{ width: '28px', color: '#6e7681', userSelect: 'none' }}>
            {idx + 1}
          </span>
          <span>{line}</span>
        </div>
      )
    })
  }

  return (
    <div className="diff-viewer">
      <div className="diff-toolbar">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <GitPullRequest size={16} color="#a855f7" />
            <span style={{ fontWeight: 600, color: '#f0f6fc', fontSize: '14px' }}>
              {patch.title}
            </span>
            {getStatusBadge()}
          </div>
          <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>
            Target: <code style={{ color: '#38bdf8' }}>{patch.file_path}</code> • {patch.explanation}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {patch.status === 'applied' ? (
            <button
              className="btn-secondary"
              onClick={async () => {
                await onRollbackPatch(patch.patch_id)
                setActionMessage('Patch successfully rolled back from disk.')
              }}
              disabled={isLoading}
              title="Revert changes from backup"
            >
              <RotateCcw size={14} />
              <span>Rollback Fix</span>
            </button>
          ) : (
            <>
              <button
                className="btn-secondary"
                onClick={async () => {
                  await onVerifyPatch(patch.patch_id)
                  setActionMessage('Executed isolated verification test suite.')
                }}
                disabled={isLoading}
                title="Run tests in sandbox with patch applied"
              >
                <Play size={14} color="#38bdf8" />
                <span>Verify in Sandbox</span>
              </button>

              <button
                className="btn-secondary"
                style={{ borderColor: 'rgba(248, 81, 73, 0.4)', color: '#f85149' }}
                onClick={() => onRejectPatch(patch.patch_id)}
                disabled={isLoading || patch.status === 'rejected'}
                title="Reject patch"
              >
                <X size={14} />
                <span>Reject</span>
              </button>

              <button
                className="btn-primary"
                style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}
                onClick={async () => {
                  await onApplyPatch(patch.patch_id)
                  setActionMessage('Patch successfully applied to disk with backup!')
                }}
                disabled={isLoading}
                title="Explicitly approve and write patch to repository file"
              >
                <Check size={14} />
                <span>Accept & Apply</span>
              </button>
            </>
          )}
        </div>
      </div>

      {actionMessage && (
        <div
          style={{
            padding: '8px 16px',
            background: 'rgba(99, 102, 241, 0.15)',
            borderBottom: '1px solid rgba(99, 102, 241, 0.3)',
            fontSize: '12px',
            color: '#38bdf8',
          }}
        >
          {actionMessage}
        </div>
      )}

      {/* Verification details */}
      {patch.test_verification && (
        <div
          style={{
            padding: '10px 16px',
            background: patch.test_verification.failed_tests === 0
              ? 'rgba(46, 160, 67, 0.1)'
              : 'rgba(248, 81, 73, 0.1)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {patch.test_verification.failed_tests === 0 ? (
              <ShieldCheck size={16} color="#3fb950" />
            ) : (
              <AlertTriangle size={16} color="#f85149" />
            )}
            <span>
              Isolated test execution:{' '}
              <strong>{patch.test_verification.passed_tests} passed</strong>,{' '}
              <strong>{patch.test_verification.failed_tests} failed</strong> of{' '}
              {patch.test_verification.total_tests} tests.
            </span>
          </div>
          <span style={{ color: '#8b949e' }}>
            {patch.test_verification.failed_tests === 0
              ? 'Fix verified: zero division crash resolved.'
              : 'Some test assertions still failing.'}
          </span>
        </div>
      )}

      <div className="diff-code-area">{renderDiffLines()}</div>
    </div>
  )
}
