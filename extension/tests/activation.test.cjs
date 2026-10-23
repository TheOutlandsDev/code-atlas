'use strict';
// Synthetic activation contract only: no Code process, project scan or real source root.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const EXT=path.dirname(__dirname),REPO=path.dirname(EXT);
const SOURCE=fs.readFileSync(path.join(EXT,'extension.js'),'utf8');
const STATE='/configured/atlas-state',WORKSPACE=STATE+'/Atlas.code-workspace';
const ROOT='/configured/source/project',REVIEWED='/configured/reviewed/Review.code-workspace';
const ID='p-0123456789abcdef';
class Uri{
 constructor(scheme,pathname){this.scheme=scheme;this.path=pathname;this.fsPath=pathname;}
 static file(p){return new Uri('file',p);}static from(value){return Object.assign(new Uri(value.scheme,value.path),value);}
 static joinPath(uri,...parts){return new Uri(uri.scheme,path.join(uri.path,...parts));}
 toString(){return this.scheme+'://'+this.path;}
}
class Emitter{constructor(){this.listeners=[];this.event=fn=>{this.listeners.push(fn);return{dispose(){}};};}fire(value){for(const fn of this.listeners)fn(value);}dispose(){this.listeners=[];}}
function host(t,{own=false,trusted=true,configured=true}={}){
 const commands=new Map(),actions=[],panels=[],intervals=[],watches=[],logs=[];let scans=0;
 const row={id:ID,rootPath:ROOT,label:'</script><img src=x onerror=bad>',languages:['Python'],primaryLanguage:'Python',status:'READ_ONLY_SOURCE',testStatus:'REVIEWED_ISOLATED_TESTS',isolatedCopyState:'NOT_CONFIGURED',sampleFiles:[],validation:{}};
 const catalog={schemaVersion:1,generation:1,projects:[row],coverage:{},validation:{mode:'static_only'}};
 const policy={bases:configured?[ROOT]:[],reviewedTests:new Map([[ROOT,{workspace:REVIEWED}]]),authorizeRoot(root){assert.equal(root,ROOT);return root;}};
 const event=()=>({dispose(){}});
 const v={Uri,EventEmitter:Emitter,ViewColumn:{One:1},FileSystemError:{NoPermissions:()=>new Error('Read only')},workspace:{workspaceFile:Uri.file(own?WORKSPACE:'/configured/other.code-workspace'),isTrusted:trusted,textDocuments:[],registerFileSystemProvider:(scheme,provider,options)=>{assert.equal(scheme,'code-atlas');assert.equal(options.isReadonly,true);return{dispose(){}};},onDidOpenTextDocument:event,onDidCloseTextDocument:event},commands:{registerCommand(id,fn){commands.set(id,fn);return{dispose(){commands.delete(id);}};},async executeCommand(...args){actions.push(args);}},window:{createOutputChannel:()=>({appendLine:value=>logs.push(value),dispose(){}}),createTreeView:()=>({reveal:async()=>{},dispose(){}}),createWebviewPanel(type,title,column,options){const messages=[];const disposed=new Emitter();const panel={options,messages,webview:{cspSource:'vscode-webview:',asWebviewUri:uri=>uri,postMessage:async value=>messages.push(value),onDidReceiveMessage:fn=>{panel.receive=fn;return{dispose(){}};},html:''},reveal(){panel.revealed=true;},onDidDispose:disposed.event,dispose(){disposed.fire();}};panels.push(panel);return panel;}}};
 class Provider{constructor(vscode,p){this.policy=p;}reconcile(){}watchOpen(){}unwatch(){}dispose(){}}
 class Tree{constructor(){}refresh(){}projectNode(){return{};}reviewedProjectId(node){if(node?.reviewed===true)return ID;throw new Error('Unknown tree node');}dispose(){}}
 class Scanner{constructor(onComplete){this.onComplete=onComplete;}request(){scans++;return Promise.resolve({status:'PASS'});}dispose(){}}
 const fakeFs={readFileSync(file,encoding){assert.equal(file,path.join(REPO,'extension/media/index.template.html'));return fs.readFileSync(file,encoding);},watchFile(file,options,fn){assert.equal(file,STATE+'/state/catalog.json');watches.push({file,fn});},unwatchFile(){}};
 const module={exports:{}};
 const context={extensionUri:Uri.file(REPO),extensionPath:REPO,subscriptions:[]};
 vm.runInNewContext(SOURCE,{module,exports:module.exports,require(name){if(name==='vscode')return v;if(name==='fs')return fakeFs;if(name==='./policy')return{ROOT:STATE,loadPolicy:()=>policy,relative:rel=>{assert.equal(typeof rel,'string');if(rel.includes('..'))throw new Error('Traversal denied');},canonical:file=>{assert.ok([WORKSPACE,REVIEWED].includes(file));return{};}};if(name==='./readonly')return{ReadonlyProvider:Provider,SCHEME:'code-atlas'};if(name==='./tree')return{SourceTree:Tree};if(name==='./scanner')return{Scanner};if(name==='./reviewed')return require('../reviewed');if(name==='./catalog')return{readCatalog:()=>catalog,emptyCatalog:()=>({projects:[],coverage:{},validation:{}}),CATALOG_FILE:STATE+'/state/catalog.json'};return require(name);},setInterval(fn,ms){const timer={fn,ms,unref(){}};intervals.push(timer);return timer;},clearInterval:timer=>timer.cleared=true,console});
 const api=module.exports.activate(context);t.after(()=>{for(const item of [...context.subscriptions].reverse())item.dispose();});
 return{api,commands,actions,panels,intervals,watches,logs,v,get scans(){return scans;}};
}
test('another trusted workspace registers navigation without automatic scan or map',t=>{const h=host(t);assert.equal(h.scans,0);assert.equal(h.panels.length,0);assert.equal(h.intervals.length,0);assert.ok(h.commands.has('codeAtlas.openMap'));assert.equal(h.watches.length,1);});
test('exact trusted dashboard opens map and bounded metadata refresh schedule',t=>{const h=host(t,{own:true});assert.equal(h.scans,1);assert.equal(h.panels.length,1);assert.equal(h.intervals[0].ms,60000);h.intervals[0].fn();assert.equal(h.scans,2);h.v.workspace.workspaceFile=Uri.file('/configured/other.code-workspace');h.intervals[0].fn();assert.equal(h.scans,2);});
test('empty explicit roots do not trigger an initial automatic scan',t=>{const h=host(t,{own:true,configured:false});assert.equal(h.scans,0);assert.equal(h.panels.length,1);});
test('untrusted dashboard starts no scan or map and denies navigation',async t=>{const h=host(t,{own:true,trusted:false});assert.equal(h.scans,0);assert.equal(h.panels.length,0);assert.equal((await h.api.scan()).status,'DENIED');assert.equal(await h.api.receiveMessage({type:'openTests',id:ID}),false);assert.deepEqual(h.actions,[]);});
test('map uses bundled local resources, restrictive CSP and escaped initial labels',t=>{const h=host(t);const panel=h.api.openMap();assert.equal(panel.options.enableCommandUris,false);assert.equal(panel.options.enableForms,false);assert.equal(panel.options.localResourceRoots.length,1);assert.equal(panel.options.localResourceRoots[0].fsPath,path.join(REPO,'extension/media'));assert.match(panel.webview.html,/default-src 'none'/);assert.match(panel.webview.html,/connect-src 'none'/);assert.match(panel.webview.html,/\\u003c\/script>/);assert.doesNotMatch(panel.webview.html,/\{\{(?:CSP|NONCE|STYLE_URI|SCRIPT_URI|INITIAL_CATALOG|INITIAL_REVIEWED_TESTS)\}\}/);assert.equal(h.scans,0);h.api.openMap();assert.equal(h.panels.length,1);});
test('reviewed workspace action opens only its configured file through VS Code API',async t=>{const h=host(t);assert.equal(await h.api.receiveMessage({type:'openTests',id:ID}),true);assert.equal(h.actions.length,1);assert.equal(h.actions[0][0],'vscode.openFolder');assert.equal(h.actions[0][1].fsPath,REVIEWED);assert.equal(h.actions[0][2].forceNewWindow,true);assert.equal(h.scans,0);});
test('extra webview command/path arguments and unknown IDs cannot open workspaces',async t=>{const h=host(t);for(const message of [{type:'openTests',id:ID,path:'/arbitrary.code-workspace'},{type:'openTests',id:'p-0000000000000000'},{type:'run',command:'arbitrary'},{type:'runAllReviewedTests',path:'/arbitrary.py'}])assert.equal(await h.api.receiveMessage(message),false);assert.deepEqual(h.actions,[]);assert.equal(h.scans,0);});
test('portable aggregate remains disabled through both public entry points',async t=>{const h=host(t);assert.equal((await h.commands.get('codeAtlas.runAllReviewedTests')()).status,'NOT_CONFIGURED');assert.equal((await h.api.receiveMessage({type:'runAllReviewedTests'})).status,'NOT_CONFIGURED');assert.equal(h.api.getReviewedTestsState().available,false);assert.equal(h.api.getReviewedTestsState().running,false);assert.equal(h.scans,0);assert.deepEqual(h.actions,[]);});
test('opening the dashboard uses its fixed local workspace path',async t=>{const h=host(t);assert.equal(await h.commands.get('codeAtlas.openWorkspace')(),true);assert.equal(h.actions[0][0],'vscode.openFolder');assert.equal(h.actions[0][1].fsPath,WORKSPACE);assert.equal(h.scans,0);});
test('source tree reviewed action rejects arbitrary node objects',async t=>{const h=host(t);assert.equal(await h.commands.get('codeAtlas.openTreeTests')({arbitrary:true}),false);assert.deepEqual(h.actions,[]);assert.equal(await h.commands.get('codeAtlas.openTreeTests')({reviewed:true}),true);assert.equal(h.actions[0][1].fsPath,REVIEWED);});
