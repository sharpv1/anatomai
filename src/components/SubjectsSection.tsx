import {catalog} from '../features/library/catalog';
import { subjects } from '../data/home';

export function SubjectsSection({ onAll }: { onAll: () => void }) {
  return <><div className="section"><h3>Предметы</h3><button className="see-all" onClick={onAll}>Все</button></div><div className="subjects">{subjects.map((subject) => <article className="subject" key={subject.title}><div className={`subject-icon ${subject.tone}`}>{subject.icon}</div><b>{subject.title}</b><small>Вопросов: {catalog.filter(e=>e.test.title.split(':')[0]===subject.title).reduce((n,e)=>n+e.questionCount,0)}</small></article>)}</div></>;
}
