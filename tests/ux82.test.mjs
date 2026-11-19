import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import ts from 'typescript';
const compile=path=>ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const uri=source=>`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const dailyUrl=uri(compile('../src/features/library/dailyTopic.ts'));
const {localDayKey,millisecondsToNextLocalDay,selectDailyTopic}=await import(dailyUrl);
const catalog=[{test:{id:'z'},questionCount:4},{test:{id:'a'},questionCount:3},{test:{id:'empty'},questionCount:0}];
test('daily topic is stable for the local day, reload and arbitrary catalog ordering',()=>{
 const start=new Date(2026,10,19,0),end=new Date(2026,10,19,23,59,59);
 assert.equal(selectDailyTopic(catalog,start).test.id,selectDailyTopic([...catalog].reverse(),end).test.id);
 assert.deepEqual(catalog.map(c=>c.test.id),['z','a','empty']);
 assert.notEqual(selectDailyTopic(catalog,start).test.id,selectDailyTopic(catalog,new Date(2026,10,20)).test.id);
 assert.equal(selectDailyTopic([],start),null);
 assert.equal(selectDailyTopic(catalog.filter(c=>c.questionCount===0),start),null);
 assert.equal(selectDailyTopic(catalog,new Date(NaN)),null);
 assert.equal(localDayKey(start),'2026-11-19');
 assert.equal(millisecondsToNextLocalDay(new Date(2026,10,19,23,59,59,999)),21);
});
test('selection uses device calendar components rather than the UTC day',()=>{
 const run=tz=>{const r=spawnSync(process.execPath,['--input-type=module','-e',`import {localDayKey,selectDailyTopic} from ${JSON.stringify(dailyUrl)};const d=new Date('2026-11-19T12:30:00Z');console.log(JSON.stringify({day:localDayKey(d),id:selectDailyTopic(${JSON.stringify(catalog)},d).test.id}));`],{encoding:'utf8',env:{...process.env,TZ:tz}});assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);};
 const utc=run('UTC'),island=run('Pacific/Kiritimati');
 assert.equal(utc.day,'2026-11-19');assert.equal(island.day,'2026-11-20');assert.notEqual(utc.id,island.id);
});
test('next local midnight respects daylight-saving transitions',()=>{
 const r=spawnSync(process.execPath,['--input-type=module','-e',`import {millisecondsToNextLocalDay} from ${JSON.stringify(dailyUrl)};console.log(millisecondsToNextLocalDay(new Date(2026,2,8)));`],{encoding:'utf8',env:{...process.env,TZ:'America/New_York'}});
 assert.equal(r.status,0,r.stderr);assert.equal(Number(r.stdout),23*3600000+20);
});
test('every Home subject ID resolves to the existing Notes discipline and bank',async()=>{
 const {subjects}=await import(uri(compile('../src/data/home.ts')));
 const dataUrl=uri(compile('../src/features/tests/data.ts'));
 const {disciplines}=await import(uri(compile('../src/features/library/catalog.ts').replace("'../tests/data'",JSON.stringify(dataUrl))));
 for(const subject of subjects){const discipline=disciplines.find(d=>d.id===subject.disciplineId);assert.ok(discipline);assert.equal(discipline.title,subject.title);}
});
