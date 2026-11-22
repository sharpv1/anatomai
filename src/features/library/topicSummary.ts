import { resultSummary } from '../tests/presentation';
import type { CompletedTest } from './statistics';
export function topicSummary(testId:string, entries:CompletedTest[]){const history=entries.filter(e=>e.result.test.id===testId);if(!history.length)return{best:null,errors:null};return{best:Math.max(...history.map(e=>resultSummary(e.result).percent)),errors:new Set(history.flatMap(e=>e.result.answers.filter(a=>a.selectedAnswer!==null&&a.selectedAnswer!==a.correctAnswer).map(a=>a.questionId))).size};}
