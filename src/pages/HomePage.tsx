import { AppHeader } from '../components/AppHeader';
import { DailyFocusCard } from '../components/DailyFocusCard';
import { StatisticsSection } from '../components/StatisticsSection';
import { SubjectsSection } from '../components/SubjectsSection';

type HomePageProps = { onStartTest: () => void; onNotify: (message: string) => void };

export function HomePage({ onStartTest, onNotify }: HomePageProps) {
  return <>
    <AppHeader onNotifications={() => onNotify('Новых уведомлений нет')} />
    <DailyFocusCard onStart={onStartTest} />
    <StatisticsSection onDetails={() => onNotify('Открываем статистику')} />
    <SubjectsSection onAll={() => onNotify('Все предметы')} />
    <div className="section"><h3>Повтори сегодня</h3><button className="see-all" onClick={() => onNotify('Открываем конспекты')}>Все конспекты</button></div>
    <section className="review"><div className="review-art">🦴</div><div className="review-copy"><b>Кости верхней конечности</b><p>12 карточек · 4 минуты на повторение</p></div><button className="review-arrow" onClick={() => onNotify('Повторение началось')}>→</button></section>
    <section className="tip"><div className="tip-icon">💡</div><div><b>Совет на сегодня</b><p>Повторяй материал короткими подходами — так знания закрепляются лучше.</p></div></section>
  </>;
}
