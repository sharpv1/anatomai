import type {User,Home,Daily,Discipline,Recommendation} from '../backend/contracts';
import {subject} from '../backend/presentation';
import { DailyQuestions } from '../components/DailyQuestions';
import type {TestDefinition} from '../features/tests/types';
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

export type ServerHome = {user:User;home:Home;daily:Daily;disciplines:Discipline[];dailyDisciplineTitle?:string|null;recommendations:Recommendation[];onDaily:(id:string)=>void};
type HomePageProps = { onStartTest: () => void; onNotify: (message: string) => void; onStatistics: () => void; onNotes: () => void; onNoteDiscipline:(id:string)=>void; onDailyReview:(test:TestDefinition)=>void; entries:CompletedTest[]; platform:TelegramPlatform;server?:ServerHome };

export function HomePage({ onStartTest, onNotify, onStatistics, onNotes, onNoteDiscipline, onDailyReview, entries, platform,server }: HomePageProps) {
  const [promoPanel, setPromoPanel] = useState<'premium' | 'mistakes' | null>(null);
  const openPromoPanel = (panel: 'premium' | 'mistakes') => {
    window.history.pushState({ homePromo: panel }, '', `#home-${panel}`);
    setPromoPanel(panel);
  };
  const closePromoPanel = () => {
    if (promoPanel && window.location.hash === `#home-${promoPanel}`) window.history.back();
    else setPromoPanel(null);
  };
  const streak=server?server.home.statistics.activity_streak_days:sessionStreak(entries);
  return <>
    <AppHeader platform={platform} verifiedUser={server?.user} onNotifications={() => onNotify('Новых уведомлений нет')} />
    <DailyFocusCard description={server?(server.home.active_attempt?`Сохранён тест «${server.home.active_attempt.title}». Возобновление здесь пока недоступно.`:server.recommendations[0]?`Повтори тему «${server.recommendations[0].title}»`:'Выбери доступную тему и начни подготовку'):undefined} onStart={onStartTest} metrics={{streakLabel:streak===null?'Серия —':`${streak} дн. подряд`,xpLabel:'XP пока недоступны'}} />
    <SubjectsSection onAll={onNotes} onSelect={onNoteDiscipline} server={server?.disciplines.slice(0,4).map(subject)} />
    <DailyQuestions onOpen={onDailyReview} server={server?.daily} disciplineLabel={server?.dailyDisciplineTitle??undefined} onServerOpen={server?.onDaily} />
    <StatisticsSection entries={entries} onDetails={onStatistics} showActivity={false} server={server?.home.statistics} />
    <StudyPromos onTests={onStartTest} onNotes={onNotes} onMistakes={() => openPromoPanel('mistakes')} onPremium={() => openPromoPanel('premium')} />
    <section className="tip"><div className="tip-icon">💡</div><div><b>Совет на сегодня</b><p>Повторяй материал короткими подходами — так знания закрепляются лучше.</p></div></section>
    {promoPanel && <PremiumDialog
      platform={platform}
      onClose={closePromoPanel}
      title={promoPanel === 'mistakes' ? 'Повторение ошибок пока недоступно' : undefined}
      description={promoPanel === 'mistakes' ? 'Отдельный режим повторения ошибок пока не реализован. Разбор ошибок доступен после завершения теста на экране результата.' : undefined}
    />}
  </>;
}
