export default function ListenButton({ appState, onTap }) {
  const isRecording  = appState === 'recording'
  const isProcessing = appState === 'processing'

  const statusMap = {
    idle:       'Tap to identify a verse',
    recording:  'Listening — tap to stop',
    processing: 'Identifying verse…',
    done:       'Tap to listen again',
    error:      'Tap to try again',
  }

  return (
    <div className="listen-wrap">
      <button
        className={`listen-btn ${isRecording ? 'recording' : ''}`}
        onClick={onTap}
        disabled={isProcessing}
        aria-label={statusMap[appState]}
      >
        {isProcessing ? (
          <span className="spinner" />
        ) : isRecording ? (
          <StopIcon />
        ) : (
          <MicIcon />
        )}
      </button>

      <div className={`waveform ${isRecording ? 'active' : ''}`}>
        {Array.from({ length: 9 }).map((_, i) => <span key={i} />)}
      </div>

      <p className="status-text">{statusMap[appState]}</p>
    </div>
  )
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="8"  y1="22" x2="16" y2="22" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  )
}
