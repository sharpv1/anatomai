import type { DailyFocusMetrics } from '../data/dailyFocus';

type DailyFocusCardProps = { onStart: () => void; metrics: DailyFocusMetrics };

export function DailyFocusCard({ onStart, metrics }: DailyFocusCardProps) {
  return (
    <section className="hero">
      <div className="hero-label">Твой фокус на сегодня</div>
      <h2>Закрепи знания за 15 минут</h2>
      <p>Короткий тест по анатомии уже ждёт тебя</p>
      <div className="focus-metrics">
        <span className="streak">{metrics.streakLabel}</span>
        <span className="micro-badge">{metrics.xpLabel}</span>
      </div>
      <button className="start" onClick={onStart}>Начать тест <span aria-hidden="true">→</span></button>
    </section>
  );
}
