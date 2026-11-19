import {catalog,disciplines} from '../features/library/catalog';
import { subjects } from '../data/home';

export function SubjectsSection({ onAll,onSelect }: { onAll: () => void;onSelect:(id:string)=>void }) {
  return <><div className="section"><h3>Предметы</h3><button className="see-all" onClick={onAll}>Все</button></div><div className="subjects">{subjects.map((subject) => <button className="subject" key={subject.disciplineId} disabled={!disciplines.some(d=>d.id===subject.disciplineId)} onClick={()=>onSelect(subject.disciplineId)}><div className={`subject-icon ${subject.tone}`}>{subject.icon}</div><b>{subject.title}</b><small>Вопросов: {catalog.filter(e=>e.test.id===subject.disciplineId).reduce((n,e)=>n+e.questionCount,0)}</small></button>)}</div></>;
}
