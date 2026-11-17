type StatisticsSectionProps = { onDetails: () => void };

export function StatisticsSection({ onDetails }: StatisticsSectionProps) {
  return (
    <>
      <div className="section"><h3>Твоя статистика</h3><button className="see-all" onClick={onDetails}>Подробнее</button></div>
      <div className="stats">
        <div className="stat"><div className="stat-icon">✓</div><div><b>78%</b><span>Средний результат</span><em className="stat-trend">↗ +8% за неделю</em></div></div>
        <div className="stat"><div className="stat-icon">◷</div><div><b>12 ч</b><span>Время обучения</span><em className="stat-trend">● 3 дня активности</em></div></div>
      </div>
      <section className="activity"><div className="activity-head"><b>Активность за неделю</b><span>16–22 ноября</span></div><div className="chart">{[34,57,82,46,66,38,25].map((height, index) => <i className={`bar ${index === 2 || index === 4 ? 'active' : index === 1 ? 'mint' : ''}`} style={{ height: `${height}%` }} key={index} />)}</div><div className="days">{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map((day) => <span key={day}>{day}</span>)}</div></section>
    </>
  );
}
