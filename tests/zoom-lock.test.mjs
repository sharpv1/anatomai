import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const js=ts.transpileModule(readFileSync(new URL('../src/platform/telegram/zoomLock.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {attachZoomLock}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
function touch(root,type,touches,changedTouches=touches,at=100){
 const event=new Event(type,{cancelable:true});Object.defineProperties(event,{touches:{value:touches},changedTouches:{value:changedTouches},timeStamp:{value:at}});root.dispatchEvent(event);return event;
}
const p=(x=10,y=10)=>({clientX:x,clientY:y});
test('pinch/gesture defaults are prevented and handlers are removed on dispose',()=>{
 const root=new EventTarget();const dispose=attachZoomLock(root);
 for(const type of ['gesturestart','gesturechange','dblclick']){const event=new Event(type,{cancelable:true});root.dispatchEvent(event);assert.equal(event.defaultPrevented,true);}
 assert.equal(touch(root,'touchstart',[p(),p(20)]).defaultPrevented,true);
 assert.equal(touch(root,'touchmove',[p(),p(30)]).defaultPrevented,true);
 dispose();dispose();
 assert.equal(touch(root,'touchmove',[p(),p(30)]).defaultPrevented,false);
 const event=new Event('gesturestart',{cancelable:true});root.dispatchEvent(event);assert.equal(event.defaultPrevented,false);
});
test('single-touch vertical/horizontal movement and clicks remain untouched',()=>{
 const root=new EventTarget();const dispose=attachZoomLock(root);
 assert.equal(touch(root,'touchstart',[p()]).defaultPrevented,false);
 assert.equal(touch(root,'touchmove',[p(10,120)]).defaultPrevented,false);
 assert.equal(touch(root,'touchend',[],[p(10,120)]).defaultPrevented,false);
 const event=new Event('click',{cancelable:true});root.dispatchEvent(event);assert.equal(event.defaultPrevented,false);dispose();
});
test('stationary double-tap is suppressed only outside interactive controls',()=>{
 const root=new EventTarget();const dispose=attachZoomLock(root);
 touch(root,'touchstart',[p()]);assert.equal(touch(root,'touchend',[],[p()],100).defaultPrevented,false);
 touch(root,'touchstart',[p()]);assert.equal(touch(root,'touchend',[],[p()],250).defaultPrevented,true);
 root.closest=()=>root;
 touch(root,'touchstart',[p()]);touch(root,'touchend',[],[p()],400);
 touch(root,'touchstart',[p()]);assert.equal(touch(root,'touchend',[],[p()],500).defaultPrevented,false);dispose();
});
