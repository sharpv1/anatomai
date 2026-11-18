import { demoDailyFocusMetrics } from '../data/dailyFocus';
import { DailyFocusCard } from '../components/DailyFocusCard';
import { SubjectsSection } from '../components/SubjectsSection';

type HomePageProps = { onStartTest: () => void; onNotes: () => void };

export function HomePage({ onStartTest, onNotes }: HomePageProps) {
  return <>
    <DailyFocusCard onStart={onStartTest} metrics={demoDailyFocusMetrics} />
    <SubjectsSection onAll={onStartTest} />
    <div className="section"><h3>Повтори сегодня</h3></div>
    <button className="review" onClick={onNotes}><span className="review-art" aria-hidden="true">🦴</span><span className="review-copy"><b>Опорно-двигательная система</b><small>Открыть конспекты</small></span><span aria-hidden="true">›</span></button>
  </>;
}
