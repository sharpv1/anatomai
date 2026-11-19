import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const source=ts.transpileModule(readFileSync(new URL('../src/features/tests/questionReview.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {correctReviewAnswers,findReviewQuestions,REVIEW_BATCH_SIZE}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const question={id:'fixture',text:'Как устроен локтевой сустав?',answers:['A','B','C'],correctAnswer:1};
test('read-only answers support scalar and explicit multiple indices; invalid indices never invent answers',()=>{
 assert.deepEqual([...correctReviewAnswers(question)],[1]);
 const multiple={...question,correctAnswer:[0,2,2,-1,9,1.5,NaN]};
 assert.deepEqual([...correctReviewAnswers(multiple)],[0,2]);
 assert.deepEqual(multiple.correctAnswer,[0,2,2,-1,9,1.5,NaN]);
 assert.equal(correctReviewAnswers({...question,correctAnswer:-1}).size,0);
 assert.equal(correctReviewAnswers({...question,correctAnswer:undefined}).size,0);
});
test('question search is case/ё/whitespace tolerant and preserves original numbering and order',()=>{
 const questions=[question,{...question,id:'q2',text:'Сколько рёбер у человека?'}];
 assert.deepEqual(findReviewQuestions(questions,'  РЕБЕР   ЧЕЛОВЕКА ').map(q=>q.number),[2]);
 assert.equal(findReviewQuestions(questions,'сустав')[0].question,question);
 assert.equal(findReviewQuestions(questions,'несуществующий').length,0);
 assert.deepEqual(findReviewQuestions(questions,' ').map(q=>q.number),[1,2]);
 assert.deepEqual(findReviewQuestions([],''),[]);
});
test('large read-only banks can be traversed in bounded batches without reordering',()=>{
 const questions=Array.from({length:2000},(_,i)=>({...question,id:`q${i}`,text:`Вопрос ${i}`}));
 const results=findReviewQuestions(questions,'');
 assert.equal(REVIEW_BATCH_SIZE,30);
 assert.equal(results.slice(0,REVIEW_BATCH_SIZE).length,30);
 assert.equal(results.slice(0,2*REVIEW_BATCH_SIZE).at(-1).number,60);
 assert.equal(results.at(-1).number,2000);
 assert.equal(questions.length,2000);
});
