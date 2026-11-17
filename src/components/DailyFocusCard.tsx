type DailyFocusCardProps = { onStart: () => void };

export function DailyFocusCard({ onStart }: DailyFocusCardProps) {
  return (
    <section className="hero">
      <div className="hero-label">Твой фокус на сегодня</div>
      <h2>Закрепи знания за 15 минут</h2>
      <p>Короткий тест по анатомии уже ждёт тебя</p>
      <div className="hero-row">
        <button className="start" onClick={onStart}>Начать тест&nbsp; →</button>
        <span className="streak">🔥 5 дней подряд</span>
      </div>
      <span className="micro-badge">✦ +120 XP за сегодня</span>
      <svg className="hero-visual" viewBox="0 0 140 160" aria-hidden="true">
        <path className="bone" d="M64 27c-8-8-6-18 2-22 8-4 15 2 14 10 1 7 6 11 11 14l-8 13c-6-3-12-8-19-15z" />
        <path className="bone" d="M76 46c-4 17-8 34-10 51-1 9-8 19-15 29l13 10c9-11 17-22 20-34 4-16 6-31 9-47z" />
        <path className="bone" d="M66 62c-12 4-23 8-34 14-9 5-16 8-22 5l-5 15c11 4 22-1 32-6l34-15z" />
        <circle className="joint" cx="76" cy="47" r="9" /><circle className="joint" cx="65" cy="98" r="8" />
        <path className="bone" d="M50 121c-8 7-16 14-23 23l10 9c7-7 15-14 25-21z" /><path className="bone" d="M88 43c8 7 16 13 26 17l-6 13c-12-5-21-11-29-20z" />
      </svg>
    </section>
  );
}
