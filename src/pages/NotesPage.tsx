import { demoTests, questionsForTest } from '../features/tests/data';

export function NotesPage() {
  return <section className="notes-page">
    <h1>Конспекты</h1>
    {demoTests.map((test) => <section key={test.id}>
      <div className="section"><h3>{test.title.split(':')[0]}</h3></div>
      {questionsForTest(test.id).map((question) => <details className="note" key={question.id}>
        <summary><span aria-hidden="true" className={`test-card-icon ${test.color}`}>{test.icon}</span>{question.text}</summary>
        <p>{question.explanation}</p>
      </details>)}
    </section>)}
  </section>;
}
