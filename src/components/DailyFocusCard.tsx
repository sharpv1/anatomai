import type { DailyFocusMetrics } from '../data/dailyFocus';

type DailyFocusCardProps = { onStart: () => void; metrics: DailyFocusMetrics; description?:string };

export function DailyFocusCard({ onStart, metrics,description }: DailyFocusCardProps) {
  return (
    <section className="hero">
      <div className="hero-label">Твой фокус на сегодня</div>
      <h2>Закрепи знания за 15 минут</h2>
      <p>{description??'Короткий тест по анатомии уже ждёт тебя'}</p>
      <div className="hero-row">
        <button className="start" onClick={onStart}>Начать тест&nbsp; →</button>
        <span className="streak">{metrics.streakLabel}</span>
      </div>
      <span className="micro-badge">{metrics.xpLabel}</span>
    </section>
  );
}
