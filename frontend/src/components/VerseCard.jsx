export default function VerseCard({ result }) {
  const { surah, ayah, surah_name, arabic_text, translation } = result

  function copyVerse() {
    const text = `${surah_name} ${surah}:${ayah}\n\n${arabic_text}\n\n${translation}`
    navigator.clipboard.writeText(text)
  }

  return (
    <div className="verse-card">
      <div className="verse-header">
        <span className="surah-badge">{surah_name} · {surah}:{ayah}</span>
      </div>

      <p className="arabic-verse">{arabic_text}</p>

      {translation && <p className="translation">{translation}</p>}

      <div className="verse-actions">
        <a
          href={`https://quran.com/${surah}/${ayah}`}
          target="_blank"
          rel="noreferrer"
          className="btn-primary"
        >
          Open in Quran.com
        </a>
        <button className="btn-secondary" onClick={copyVerse}>
          Copy verse
        </button>
      </div>
    </div>
  )
}
