import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const compile=path=>ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const url=js=>`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`;
const dataUrl=url(compile('../src/features/tests/data.ts'));
const source=compile('../src/features/library/catalog.ts').replace("'../tests/data'",JSON.stringify(dataUrl));
const {catalog,disciplines,levels,matchesSearch,profileDisplayName,telegramProfile}=await import(url(source));
test('catalog counts loaded questions rather than demo metadata or progress',()=>{
 assert.deepEqual(catalog.map(item=>item.questionCount),[5,3,1,1]);assert.equal(catalog[0].test.meta.startsWith('20 вопросов'),true);
 assert.deepEqual(disciplines.map(item=>item.title),['Анатомия','Физиология','Неврология','Гистология']);
 assert.equal(new Set(disciplines.map(item=>item.id)).size,4);assert.deepEqual(new Set(levels),new Set(['Средний','Легко','Сложно']));
});
test('client search handles Russian case, spaces, ё and empty queries',()=>{
 assert.equal(matchesSearch('Неврология',' НЕВРО '),true);assert.equal(matchesSearch('Учёба','учеба'),true);assert.equal(matchesSearch('Анатомия',''),true);assert.equal(matchesSearch('Анатомия','ткани'),false);
});
test('profile display name uses only supplied Telegram data and handles malformed/absent users',()=>{
 const encode=user=>new URLSearchParams({user:JSON.stringify(user)}).toString();
 assert.equal(profileDisplayName(encode({first_name:'Айдана',last_name:'Садыкова'})),'Айдана Садыкова');
 assert.equal(profileDisplayName(encode({username:'student'})),'@student');
 for(const value of [undefined,'','user=not-json',encode(null),encode([]),encode({first_name:12,last_name:{}}),encode({})])assert.equal(profileDisplayName(value),null);
});

test('Telegram avatar uses provided HTTPS photo and supports SDK user fallback',()=>{
 const initData=new URLSearchParams({user:JSON.stringify({first_name:'Айдана',photo_url:'https://example.com/avatar.jpg'})}).toString();
 assert.deepEqual(telegramProfile({initData}),{name:'Айдана',photoUrl:'https://example.com/avatar.jpg'});
 assert.deepEqual(telegramProfile({initDataUnsafe:{user:{first_name:'Анна',last_name:' Иванова ',photo_url:'https://example.com/a.png'}}}),{name:'Анна Иванова',photoUrl:'https://example.com/a.png'});
 for(const photo_url of ['http://example.com/a','javascript:alert(1)','data:image/png;base64,abc','not a URL','https://user:pass@example.com/a']){
  assert.equal(telegramProfile({initDataUnsafe:{user:{first_name:'Анна',photo_url}}}).photoUrl,null);
 }
 assert.deepEqual(telegramProfile(),{name:null,photoUrl:null});
});
