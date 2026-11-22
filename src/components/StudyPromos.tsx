import './StudyPromos.css';

type StudyPromosProps = {
  onTests: () => void;
  onNotes: () => void;
  onMistakes: () => void;
  onPremium: () => void;
};

export function StudyPromos({ onTests, onNotes, onMistakes, onPremium }: StudyPromosProps) {
  const banners = [
    { image: 'exam-preparation.webp', label: 'Подготовка к экзаменам — открыть тесты', action: onTests },
    { image: 'medical-notes.webp', label: 'Конспекты — открыть раздел', action: onNotes },
    { image: 'mistake-review.webp', label: 'Повторение ошибок — информация о доступности', action: onMistakes },
    { image: 'anatomai-premium.webp', label: 'Premium — подробнее о расширенном доступе', action: onPremium },
  ];

  return (
    <section className="study-promos" aria-label="Учиться с ANATOMAI">
      {banners.map(banner => (
        <button
          key={banner.image}
          className={`study-promo study-promo--image${banner.image === 'anatomai-premium.webp' ? ' study-promo--premium' : ''}`}
          aria-label={banner.label}
          onClick={banner.action}
        >
          <img
            className="study-promo__artwork"
            src={`${import.meta.env.BASE_URL}promos/${banner.image}`}
            alt=""
            width={1536}
            height={768}
            loading="lazy"
            decoding="async"
          />
          {banner.image === 'anatomai-premium.webp' && <img
            className="study-promo__headroom"
            src={`${import.meta.env.BASE_URL}promos/${banner.image}`}
            alt=""
            aria-hidden="true"
            width={1536}
            height={768}
            loading="lazy"
            decoding="async"
          />}
        </button>
      ))}
    </section>
  );
}
