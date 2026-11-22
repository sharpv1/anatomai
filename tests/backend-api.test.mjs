import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const url=source=>`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const compile=file=>ts.transpileModule(readFileSync(new URL('../src/backend/'+file,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const contractsUrl=url(compile('contracts.ts'));
const clientUrl=url(compile('client.ts').replaceAll("'./contracts'",JSON.stringify(contractsUrl)));
const authUrl=url(compile('auth.ts').replaceAll("'./contracts'",JSON.stringify(contractsUrl)).replaceAll("'./client'",JSON.stringify(clientUrl)));
const {ApiClient,ApiError,apiBase,query}=await import(clientUrl);
const {AuthController,launchData}=await import(authUrl);
const dto=await import(contractsUrl);
const envelope=data=>({data,meta:{request_id:'synthetic-request',server_time:new Date().toISOString(),schema_version:'1'}});
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
const ok=data=>response(envelope(data));
const denied=()=>response({error:{code:'AUTH_REQUIRED',request_id:'synthetic-error'}},401);
const user=id=>({id:'owner-'+id,telegram_user_id:String(id),first_name:'SYNTHETIC '+id,last_name:null,username:null,photo_url:null,timezone:'UTC',language:'ru',version:1,roles:['student']});
const session=id=>({id:'session-'+id,user:user(id),csrf_token:'csrf-'+id,expires_at:new Date(Date.now()+3600000).toISOString(),idle_expires_at:new Date(Date.now()+3600000).toISOString()});
const launch=id=>({initData:'SYNTHETIC-LAUNCH-'+id,userHint:String(id)});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

test('API sends credentials/no-store/redirect protection; CSRF only on authenticated mutations',async()=>{
 const calls=[];const c=new ApiClient(async(path,options)=>{calls.push({path,options});return ok({});});
 await c.raw('/me');assert.equal(calls[0].path,'/api/v1/me');assert.equal(calls[0].options.credentials,'include');assert.equal(calls[0].options.cache,'no-store');assert.equal(calls[0].options.redirect,'error');
 await assert.rejects(c.raw('/me/preferences',{method:'PATCH',body:{timezone:'UTC'}}),e=>e.code==='CSRF_REQUIRED');
 c.setCsrf('csrf-memory-only');await c.raw('/me/preferences',{method:'PATCH',body:{timezone:'UTC'}});
 assert.equal(calls[1].options.headers['X-CSRF-Token'],'csrf-memory-only');
 await c.raw('/auth/telegram',{method:'POST',auth:false,body:{init_data:'synthetic'}});
 assert.equal(calls[2].options.headers['X-CSRF-Token'],undefined);
 assert.equal(calls[0].options.headers.Authorization,undefined);
 assert.equal(query({query:'сердце & лёгкие',limit:30,cursor:null}),'?query=%D1%81%D0%B5%D1%80%D0%B4%D1%86%D0%B5+%26+%D0%BB%D1%91%D0%B3%D0%BA%D0%B8%D0%B5&limit=30');
});
test('same-origin configuration and paths cannot exfiltrate credentials',async()=>{
 for(const base of ['https://production.example/api','//other.test/api','/api/../auth','/api#fragment','/api?host=evil'])assert.throws(()=>apiBase(base));
 assert.equal(apiBase('/api/v1/'),'/api/v1');
 assert.throws(()=>new ApiClient(fetch,'https://other.test/api'));
 const c=new ApiClient(async()=>{throw Error('must not request');});
 for(const path of ['https://other.test','//other.test/','/../outside','/me#token'])await assert.rejects(c.raw(path),e=>e.code==='INVALID_API_PATH');
});
test('network failures, timeout, cancellation, protocol errors and server request IDs are distinct',async()=>{
 const network=new ApiClient(async()=>{throw Error('internal sensitive transport error');});
 await assert.rejects(network.raw('/me'),e=>e.code==='NETWORK'&&!e.message.includes('sensitive'));
 const timed=new ApiClient((_,{signal})=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))),undefined,5);
 await assert.rejects(timed.raw('/me'),e=>e.code==='TIMEOUT');
 const invalid=new ApiClient(async()=>new Response('not-json'));
 await assert.rejects(invalid.raw('/me'),e=>e.code==='INVALID_RESPONSE');
 const malformed=new ApiClient(async()=>ok({completed_tests:'fake'}));
 await assert.rejects(malformed.get('/me/statistics',dto.summary),e=>e.code==='INVALID_DTO');
 const refused=new ApiClient(async()=>response({error:{code:'EXAM_REFERENCE_LOCKED',message:'not displayed',request_id:'trace-1'}},409));
 await assert.rejects(refused.raw('/topics/x/reference-questions'),e=>e.code==='EXAM_REFERENCE_LOCKED'&&e.requestId==='trace-1');
});
test('reset aborts personal requests and rejects late responses even when transport ignores cancellation',async()=>{
 let release;const c=new ApiClient(()=>new Promise(resolve=>release=resolve));
 c.setCsrf('old-csrf');const pending=c.raw('/me');c.reset();release(ok({old:'personal data'}));
 await assert.rejects(pending,e=>e.code==='CANCELLED');
 await assert.rejects(c.raw('/me/preferences',{method:'PATCH'}),e=>e.code==='CSRF_REQUIRED');
});
test('first login verifies via existing Identity and confirms cookie before publishing ready',async()=>{
 let signedIn=false;const calls=[];
 const c=new ApiClient(async(path,options)=>{calls.push(path);if(path==='/api/v1/auth/telegram'){assert.equal(JSON.parse(options.body).init_data,'SYNTHETIC-LAUNCH-1');signedIn=true;return ok(session(1));}return signedIn?ok(session(1)):denied();});
 const auth=new AuthController(c,()=>launch(1));await auth.bootstrap();
 assert.equal(auth.getSnapshot().status,'ready');assert.equal(auth.getSnapshot().session.user.id,'owner-1');
 assert.deepEqual(calls,['/api/v1/auth/session','/api/v1/auth/telegram','/api/v1/auth/session']);auth.dispose();
});
test('reopen restores an existing session without replaying login; valid browser cookie can restore without initData',async()=>{
 const calls=[];const c=new ApiClient(async path=>{calls.push(path);return ok(session(1));});
 let current=launch(1);const auth=new AuthController(c,()=>current);
 await auth.bootstrap();await auth.bootstrap();current={initData:'',userHint:null};await auth.bootstrap();
 assert.equal(auth.getSnapshot().status,'ready');assert.deepEqual(calls,Array(3).fill('/api/v1/auth/session'));auth.dispose();
});
test('no initData, stale initData, blocked cookies and network failures fail closed; retry recovers',async()=>{
 const missing=new AuthController(new ApiClient(async()=>denied()),()=>({initData:'',userHint:null}));await missing.bootstrap();assert.equal(missing.getSnapshot().error.code,'INIT_DATA_REQUIRED');missing.dispose();
 const blocked=new AuthController(new ApiClient(async path=>path.endsWith('/telegram')?ok(session(1)):denied()),()=>launch(1));await blocked.bootstrap();assert.equal(blocked.getSnapshot().status,'error');blocked.dispose();
 const stale=new AuthController(new ApiClient(async path=>path.endsWith('/telegram')?response({error:{code:'INIT_DATA_EXPIRED'}},401):denied()),()=>launch(1));await stale.bootstrap();assert.equal(stale.getSnapshot().status,'error');stale.dispose();
 let offline=true;const recovered=new AuthController(new ApiClient(async()=>{if(offline)throw Error('offline');return ok(session(1));}),()=>launch(1));await recovered.bootstrap();assert.equal(recovered.getSnapshot().status,'error');offline=false;await recovered.bootstrap();assert.equal(recovered.getSnapshot().status,'ready');recovered.dispose();
});
test('session expiry clears UI and restores through Identity without retrying the original mutation',async()=>{
 let signedIn=false,reads=0;
 const c=new ApiClient(async(path)=>{if(path.endsWith('/telegram')){signedIn=true;return ok(session(1));}if(path.endsWith('/session'))return signedIn?ok(session(1)):denied();reads++;signedIn=false;return denied();});
 const auth=new AuthController(c,()=>launch(1));await auth.bootstrap();assert.equal(auth.getSnapshot().status,'ready');
 await assert.rejects(c.raw('/me/statistics'));assert.equal(auth.getSnapshot().status,'checking');
 for(let i=0;i<10&&auth.getSnapshot().status==='checking';i++)await tick();
 assert.equal(auth.getSnapshot().status,'ready');assert.equal(reads,1);auth.dispose();
});
test('switching Telegram users cannot publish the previous identity or late response',async()=>{
 let current=launch(1),cookie=1,release;
 const c=new ApiClient(async(path,options)=>{if(path.endsWith('/telegram')){cookie=JSON.parse(options.body).init_data.endsWith('2')?2:1;return ok(session(cookie));}if(release===undefined&&current.userHint==='1')return new Promise(resolve=>release=resolve);return ok(session(cookie));});
 const auth=new AuthController(c,()=>current);const first=auth.bootstrap();await tick();current=launch(2);const second=auth.bootstrap();assert.equal(auth.getSnapshot().status,'checking');release(ok(session(1)));await first;await second;
 assert.equal(auth.getSnapshot().status,'ready');assert.equal(auth.getSnapshot().session.user.telegram_user_id,'2');auth.dispose();
});
test('unsafe SDK identity is only a switch hint; absent proof cannot switch an existing cookie',async()=>{
 assert.deepEqual(launchData({initDataUnsafe:{user:{id:2}}}),{initData:'',userHint:'2'});
 const auth=new AuthController(new ApiClient(async()=>ok(session(1))),()=>({initData:'',userHint:'2'}));
 await auth.bootstrap();assert.equal(auth.getSnapshot().status,'error');auth.dispose();
});
test('read-only DTOs reject invented counters and answer keys not in supplied options',()=>{
 assert.throws(()=>dto.reference({question_id:'q',revision_id:'r',number:1,kind:'single_choice',text:'question',options:[{id:'a',position:0,code:'A',text:'a'},{id:'b',position:1,code:'B',text:'b'}],correct_option_ids:['foreign']}));
 assert.throws(()=>dto.summary({completed_tests:-1}));
 assert.throws(()=>dto.listEnvelope({data:[],meta:{},page:{has_more:true,next_cursor:null}},dto.discipline));
});

test('contradictory SDK account hints fail closed until fresh launch data arrives',async()=>{
 const launch=launchData({initData:new URLSearchParams({user:JSON.stringify({id:1})}).toString(),initDataUnsafe:{user:{id:2}}});
 assert.equal(launch.conflictingIdentity,true);
 let requests=0;const auth=new AuthController(new ApiClient(async()=>{requests++;return ok(session(1));}),()=>launch);
 await auth.bootstrap();assert.equal(auth.getSnapshot().status,'error');assert.equal(requests,0);auth.dispose();
});
test('invalid launch user must be verified even if unsafe hint matches an existing cookie',async()=>{
 const launch=launchData({initData:'malformed',initDataUnsafe:{user:{id:1}}});
 assert.equal(launch.requiresVerification,true);
 let posts=0;const auth=new AuthController(new ApiClient(async path=>{if(path.endsWith('/telegram')){posts++;return response({error:{code:'INVALID_INIT_DATA'}},401);}return ok(session(1));}),()=>launch);
 await auth.bootstrap();assert.equal(auth.getSnapshot().status,'error');assert.equal(posts,1);auth.dispose();
});
test('feature flag is opt-in and disabled mode never validates or uses a remote URL',async()=>{
 const configUrl=url(compile('config.ts').replaceAll("'./client'",JSON.stringify(clientUrl)).replaceAll('import.meta.env','{}'));
 const {integrationConfig}=await import(configUrl);
 assert.equal(integrationConfig({}).enabled,false);
 assert.equal(integrationConfig({VITE_MEDEXA_BACKEND_ENABLED:'false',VITE_MEDEXA_API_BASE:'https://production.invalid'}).enabled,false);
 assert.equal(integrationConfig({VITE_MEDEXA_BACKEND_ENABLED:'1'}).enabled,false);
 assert.equal(integrationConfig({VITE_MEDEXA_BACKEND_ENABLED:'true'}).base,'/api/v1');
 assert.throws(()=>integrationConfig({VITE_MEDEXA_BACKEND_ENABLED:'true',VITE_MEDEXA_API_BASE:'https://production.invalid'}));
});

test('Telegram launch requires the server path without opting in; SDK shell alone is not a launch', async()=>{
 const configUrl=url(compile('config.ts').replaceAll("'./client'",JSON.stringify(clientUrl)).replaceAll('import.meta.env','{}'));
 const {hasTelegramLaunch}=await import(configUrl);
 assert.equal(hasTelegramLaunch(undefined),false);
 assert.equal(hasTelegramLaunch(undefined,'#tgWebAppData=opaque&tgWebAppPlatform=ios'),true);
 assert.equal(hasTelegramLaunch(undefined,'?tgWebAppPlatform=ios'),true);
 assert.equal(hasTelegramLaunch(undefined,'#topic'),false);
 for(const initData of ['', '  ', null, 17])assert.equal(hasTelegramLaunch({initData}),false);
 for(const initData of ['auth_date=1&user=...&hash=...', 'malformed-proof'])assert.equal(hasTelegramLaunch({initData}),true);
 // Routing is fail-closed; only Identity is allowed to accept/reject the proof.
});

test('server selection validates its configured base even when browser opt-in is false',async()=>{
 const configUrl=url(compile('config.ts').replaceAll("'./client'",JSON.stringify(clientUrl)).replaceAll('import.meta.env','{}'));
 const {integrationConfig}=await import(configUrl);
 const env={VITE_MEDEXA_BACKEND_ENABLED:'false',VITE_MEDEXA_API_BASE:'/custom/api/v1'};
 assert.deepEqual(integrationConfig(env,true),{enabled:false,base:'/custom/api/v1'});
 assert.throws(()=>integrationConfig({...env,VITE_MEDEXA_API_BASE:'https://outside.invalid'},true));
});
