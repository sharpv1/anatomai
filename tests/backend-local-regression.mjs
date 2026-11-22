/** Run the existing UI 8.3 regression unchanged, with isolated output and browser path. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const target=process.env.AFTER_URL??'http://127.0.0.1:5180';
assert.ok(['127.0.0.1','localhost'].includes(new URL(target).hostname),'Loopback test server required');
const temporary=new URL('./.backend-ui83-check.mjs',import.meta.url);
try{
 const source=readFileSync(new URL('./ui83.mjs',import.meta.url),'utf8')
  .replace("const dir='docs/screenshots/ui-8.3'","const dir='/tmp/medexa6a-local-regression'")
  .replace("executablePath:'/usr/bin/chromium'","executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium'");
 writeFileSync(temporary,source);
 const run=spawnSync(process.execPath,[fileURLToPath(temporary)],{stdio:'inherit',env:{...process.env,AFTER_URL:target}});
 process.exitCode=run.status??1;
}finally{rmSync(temporary,{force:true});}
