import './StudyPromos.css';

type StudyPromosProps = {
  onTests: () => void;
  onNotes: () => void;
};

export function StudyPromos({ onTests, onNotes }: StudyPromosProps) {
  const banners = [
    { image: 'promo-tests.png', label: 'Проверь свои знания — открыть тесты', action: onTests },
    { image: 'promo-notes.png', label: 'Повторяй главное — открыть конспекты', action: onNotes },
    { image: 'promo-exams.png', label: 'Готовься к экзаменам — открыть каталог тестов', action: onTests },
  ];

  return (
    <section className="study-promos" aria-label="Учиться с ANATOMAI">
      {banners.map(banner => (
        <button
          key={banner.image}
          className="study-promo study-promo--image"
          aria-label={banner.label}
          onClick={banner.action}
        >
          <img
            src={`${import.meta.env.BASE_URL}promos/${banner.image}`}
            alt=""
            width={1774}
            height={887}
            loading="lazy"
            decoding="async"
          />
        </button>
      ))}
    </section>
  );
}
