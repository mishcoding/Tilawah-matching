import { useState, useRef } from 'react'
import ListenButton from './components/ListenButton'
import VerseCard from './components/VerseCard'
import './App.css'

const BACKEND = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default function App() {
  const [appState, setAppState]       = useState('idle')
  const [result, setResult]           = useState(null)
  const [errorMsg, setErrorMsg]       = useState('')
  const [whisperText, setWhisperText] = useState('')

  const mediaRecorderRef = useRef(null)
  const chunksRef        = useRef([])

  async function startRecording() {
    setResult(null)
    setErrorMsg('')
    setWhisperText('')

    try {
      const stream   = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunksRef.current = []

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/mp4'

      const recorder = new MediaRecorder(stream, { mimeType })
      recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = () => sendToBackend(mimeType)
      recorder.start()

      mediaRecorderRef.current = recorder
      setAppState('recording')
    } catch {
      setErrorMsg('Microphone permission denied. Please allow access and try again.')
      setAppState('error')
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop()
    mediaRecorderRef.current?.stream.getTracks().forEach(t => t.stop())
    setAppState('processing')
  }

  async function sendToBackend(mimeType) {
    const blob     = new Blob(chunksRef.current, { type: mimeType })
    const formData = new FormData()
    formData.append('audio',     blob, `recording.${mimeType.includes('mp4') ? 'mp4' : 'webm'}`)
    formData.append('mime_type', mimeType)

    try {
      const res  = await fetch(`${BACKEND}/identify`, { method: 'POST', body: formData })
      const data = await res.json()

      if (!res.ok) throw new Error(data.detail || 'Server error')

      setWhisperText(data.whisper_text)
      setResult(data)
      setAppState('done')
    } catch (err) {
      setErrorMsg(err.message)
      setAppState('error')
    }
  }

  function handleTap() {
    if (['idle', 'done', 'error'].includes(appState)) startRecording()
    else if (appState === 'recording') stopRecording()
  }

  return (
    <div className="app">
      <header>
        <span className="wordmark">Ayah</span>
        <span className="arabic-title">آية</span>
        <p className="tagline">Identify any Quranic verse by listening</p>
      </header>

      <main>
        <ListenButton appState={appState} onTap={handleTap} />

        {errorMsg && <div className="error-msg">{errorMsg}</div>}

        {result && <VerseCard result={result} />}

        {whisperText && appState === 'done' && (
          <p className="whisper-debug">Whisper heard: {whisperText}</p>
        )}
      </main>

      <footer>Made with care · Ramadan 1447</footer>
    </div>
  )
}
