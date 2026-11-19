import { StudyPromos } from '../components/StudyPromos';
import { useState } from 'react';
import { PremiumDialog } from '../features/library/PremiumDialog';
import type {CompletedTest} from '../features/library/statistics';
import type {TelegramPlatform} from '../platform/telegram/TelegramPlatformAdapter';
import {sessionStreak} from '../features/library/achievements';
import { AppHeader } from '../components/AppHeader';
import { DailyFocusCard } from '../components/DailyFocusCard';
import { StatisticsSection } from '../components/StatisticsSection';
import { SubjectsSection } from '../components/SubjectsSection';

type HomePageProps = { onStartTest: () => void; onNotify: (message: string) => void; onStatistics: () => void; onNotes: () => void; entries:CompletedTest[]; platform:TelegramPlatform };

export function HomePage({ onStartTest, onNotify, onStatistics, onNotes, entries, platform }: HomePageProps) {
  const [promoPanel, setPromoPanel] = useState<'premium' | 'mistakes' | null>(null);
  const openPromoPanel = (panel: 'premium' | 'mistakes') => {
    window.history.pushState({ homePromo: panel }, '', `#home-${panel}`);
    setPromoPanel(panel);
  };
  const closePromoPanel = () => {
    if (promoPanel && window.location.hash === `#home-${promoPanel}`) window.history.back();
    else setPromoPanel(null);
  };
  const streak=sessionStreak(entries);
  return <>
    <AppHeader platform={platform} onNotifications={() => onNotify('Новых уведомлений нет')} />
    <DailyFocusCard onStart={onStartTest} metrics={{streakLabel:streak===null?'Серия —':`${streak} дн. подряд`,xpLabel:'XP пока недоступны'}} />
    <StudyPromos onTests={onStartTest} onNotes={onNotes} onMistakes={() => openPromoPanel('mistakes')} onPremium={() => openPromoPanel('premium')} />
    <StatisticsSection entries={entries} onDetails={onStatistics} />
    <SubjectsSection onAll={() => onNotify('Все предметы')} />
    <div className="section"><h3>Повтори сегодня</h3><button className="see-all" onClick={() => onNotify('Открываем конспекты')}>Все конспекты</button></div>
    <section className="review"><div className="review-art">🦴</div><div className="review-copy"><b>Кости верхней конечности</b><p>12 карточек · 4 минуты на повторение</p></div><button className="review-arrow" onClick={() => onNotify('Повторение началось')}>→</button></section>
    <section className="tip"><div className="tip-icon">💡</div><div><b>Совет на сегодня</b><p>Повторяй материал короткими подходами — так знания закрепляются лучше.</p></div></section>
    {promoPanel && <PremiumDialog
      platform={platform}
      onClose={closePromoPanel}
      title={promoPanel === 'mistakes' ? 'Повторение ошибок пока недоступно' : undefined}
      description={promoPanel === 'mistakes' ? 'Отдельный режим повторения ошибок пока не реализован. Разбор ошибок доступен после завершения теста на экране результата.' : undefined}
    />}
  </>;
}
