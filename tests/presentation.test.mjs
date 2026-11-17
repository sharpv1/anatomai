import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const js = ts.transpileModule(readFileSync(new URL('../src/features/tests/presentation.ts', import.meta.url), 'utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {answerState, correctStreak}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
test('selection never reveals correctness before confirmation',()=>{
  assert.equal(answerState(1,null,null,1),'idle');
  assert.equal(answerState(1,1,null,1),'selected');
  assert.equal(answerState(1,0,null,1),'idle');
  assert.equal(answerState(0,0,null,1),'selected');
});
test('confirmation reveals correct and incorrect cards; other cards stay idle',()=>{
  assert.equal(answerState(1,0,0,1),'correct');
  assert.equal(answerState(0,0,0,1),'wrong');
  assert.equal(answerState(2,0,0,1),'idle');
  assert.equal(answerState(1,1,1,1),'correct');
});
test('streak counts only consecutive confirmed correct answers and resets on skip/error',()=>{
  const a=(selected,correct=1)=>({questionId:'q',selectedAnswer:selected,correctAnswer:correct});
  assert.equal(correctStreak([],null,1),0);
  assert.equal(correctStreak([a(1),a(1)],null,1),2);
  assert.equal(correctStreak([a(1)],1,1),2);
  assert.equal(correctStreak([a(1)],0,1),0);
  assert.equal(correctStreak([a(1),a(null)],null,1),0);
  assert.equal(correctStreak([a(0),a(1)],1,1),2);
});
