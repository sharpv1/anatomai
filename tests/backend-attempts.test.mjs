import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import {fixture,id,envelope,ok,fail,clone,complete} from './attempt-fixtures.mjs';
const url=s=>`data:text/javascript;base64,${Buffer.from(s).toString('base64')}`;
const compile=f=>ts.transpileModule(readFileSync(new URL('../src/backend/'+f,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const contracts=url(compile('contracts.ts'));const client=url(compile('client.ts').replaceAll("'./contracts'",JSON.stringify(contracts)));
const attempts=url(compile('attempts.ts').replaceAll("'./contracts'",JSON.stringify(contracts)).replaceAll("'./client'",JSON.stringify(client)));
const {ApiClient}=await import(client);const {AttemptController,attempt,etag,examReview}=await import(attempts);
const api=f=>{const c=new ApiClient(f);c.setCsrf('synthetic-csrf');return c;};
const controller=f=>new AttemptController(api(f),'owner',()=>id(99));
test('allowlist rejects active exam answer keys, option flags, feedback, result and explanations',()=>{
 for(const decorate of [a=>a.current_item.feedback={is_correct:true},a=>a.current_item.explanation='secret',a=>a.current_item.correct_option_ids=[id(7)],a=>a.current_item.options[0].is_correct=true,a=>a.result=complete(fixture()).result,a=>a.correct_option_ids=[id(7)]]) {const a=fixture('exam');decorate(a);assert.throws(()=>attempt(a));}
 assert.equal(attempt(fixture('exam')).mode,'exam');assert.equal(attempt(fixture()).current_item.state,'awaiting_answer');
});
test('checked learning validates feedback membership and terminal result invariants',()=>{
 const a=fixture();a.current_item.state='checked';a.current_item.selected_option_ids=[id(8)];a.current_item.feedback={is_correct:false,correct_option_ids:[id(7)],explanation:'Из опубликованной редакции'};assert.equal(attempt(a).current_item.feedback.is_correct,false);
 a.current_item.feedback.correct_option_ids=[id(100)];assert.throws(()=>attempt(a));const b=complete(fixture());b.result.correct=9;assert.throws(()=>attempt(b));
});
test('immutable intent uses CSRF, UUID key, PUT and original If-Match on exact retry; ignores historical replay projection',async()=>{
 let a=fixture('exam'),lost=true;const calls=[];
 const c=controller(async(path,o)=>{if(o.method==='PUT'){calls.push(o);if(lost){a.version++;a.current_item.selected_option_ids=[id(7)];lost=false;throw Error('lost HTTP response');}return ok(fixture('exam'));}return ok(clone(a));});
 await c.refresh(id(1));await c.action('draft',id(7));assert.equal(c.getSnapshot().value.version,2);assert.ok(c.getSnapshot().pending);await c.refresh();assert.ok(c.getSnapshot().pending);await c.action('finish');assert.equal(calls.length,1);
 await c.retry();assert.equal(calls.length,2);for(const o of calls){assert.equal(o.headers['Idempotency-Key'],id(99));assert.equal(o.headers['If-Match'],etag(fixture('exam')));assert.equal(o.headers['X-CSRF-Token'],'synthetic-csrf');assert.equal(o.credentials,'include');assert.deepEqual(JSON.parse(o.body),{selected_option_ids:[id(7)]});}assert.equal(c.getSnapshot().value.version,2);assert.equal(c.getSnapshot().pending,null);
});
test('409/412 reconcile without silently replaying, changing keys or starting another attempt',async()=>{
 for(const status of [409,412]) {let calls=0,a=fixture();const c=controller(async(p,o)=>{if(o.method==='POST'){calls++;a.version++;return fail(status,'ATTEMPT_VERSION_CONFLICT');}return ok(clone(a));});await c.refresh(id(1));await c.action('skip');assert.equal(c.getSnapshot().value.version,2);assert.equal(c.getSnapshot().pending,null);assert.equal(calls,1);await c.retry();assert.equal(calls,1);}
});
test('double submit/finish is locked synchronously',async()=>{
 let resolve,calls=0,a=fixture();const c=controller(async(p,o)=>{if(o.method==='POST'){calls++;await new Promise(r=>resolve=r);return ok(clone(a));}return ok(clone(a));});await c.refresh(id(1));const first=c.action('submit',id(7));await c.action('submit',id(8));await c.action('finish');assert.equal(calls,1);resolve();await first;
});
test('start response loss uses active-attempt reconciliation and retries original start, not a second automatic create',async()=>{
 let a=null,calls=0;const c=controller(async(p,o)=>{if(o.method==='POST'){calls++;a=fixture();throw Error('network');}return ok(a);});await c.start('learning',{topic_id:id(3)});assert.equal(calls,1);assert.equal(c.getSnapshot().value.id,id(1));assert.equal(c.getSnapshot().pending.path,'/attempts');await c.start('exam',{topic_id:id(3)});assert.equal(calls,1);
});
test('401 retains original request for explicit retry after Identity restores the session',async()=>{
 let denied=true,calls=0;const client=api(async(p,o)=>{if(o.method==='POST'){calls++;return denied?fail(401,'AUTH_REQUIRED'):ok(fixture());}return ok(fixture());});let auth=0;client.onUnauthorized=()=>auth++;const c=new AttemptController(client,'owner',()=>id(99));await c.refresh(id(1));await c.action('skip');assert.equal(auth,1);assert.ok(c.getSnapshot().pending);denied=false;await c.retry();assert.equal(calls,2);assert.equal(c.getSnapshot().pending,null);
});
test('owner disposal drops sensitive state and rejects late responses from old account',async()=>{
 let release;const c=controller(()=>new Promise(r=>release=r));const pending=c.refresh(id(1));c.dispose();release(ok(fixture()));await pending;assert.equal(c.getSnapshot().value,null);assert.equal(c.getSnapshot().pending,null);assert.equal(c.getSnapshot().loaded,false);
});
test('server completed timeout is authoritative; no local re-scoring or auto-start',async()=>{
 const done=complete(fixture('exam'),'timeout');const c=controller(async()=>ok(done));await c.refresh(id(1));assert.equal(c.getSnapshot().value.result.percent,50);assert.equal(c.getSnapshot().value.result.finish_reason,'timeout');await c.action('draft',id(7));assert.equal(c.getSnapshot().value.version,done.version);
});
test('safe review decoder accepts completed snapshot with skipped response',()=>{
 const item=fixture().current_item;delete item.state;item.correct_option_ids=[id(7)];item.is_correct=null;
 assert.equal(examReview({items:[item],total:1,next_offset:null}).items.length,1);
});
