'use strict';
// Original synthetic native checks. Copyright 2026 TheOutlandsDev. MIT.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vscode = require('vscode');
const {spawnSync} = require('node:child_process');

exports.run = async function run() {
  const session = process.env.ATLAS_ACCEPTANCE_SESSION;
  assert.ok(session && path.isAbsolute(session),'Explicit acceptance session required');
  const context = JSON.parse(fs.readFileSync(path.join(session,'session.json'),'utf8'));
  assert.equal(context.kind,'code-atlas-native-acceptance-v1');
  assert.equal(context.session,session);
  assert.equal(context.fixtures,path.join(session,'fixtures'));
  assert.equal(context.state,path.join(session,'state'));
  assert.equal(fs.realpathSync(session),session);
  const phase = process.env.ATLAS_ACCEPTANCE_PHASE;
  assert.ok(['untrusted-before','first','restart','untrusted-after'].includes(phase));
  const report = {status:'RUNNING',platform:process.platform,vscodeVersion:vscode.version,phase,
    extension:'TheOutlandsDev.code-atlas',syntheticOnly:true,checks:[],manualWebviewAcceptance:'NOT_RUN_BY_NATIVE_API_TEST',
    scope:'Native VS Code APIs, published VSIX and disposable fixtures only. Not a private-project or production check.'};
  const output = path.join(session,'native-'+phase+'.json');
  const save = () => fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n',{mode:0o600});
  const check = (name, value) => { if(!value)report.failedCheck=name; assert.ok(value,name);report.checks.push({name,result:'PASS'});save(); };
  const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
  const capture = async name => {
    await pause(1500);
    const file = path.join(session,phase+'-'+name+'.png');
    const result = spawnSync('import',['-window','root',file],{timeout:15000});
    assert.equal(result.status,0,'Native virtual-display capture succeeded');
    assert.ok(fs.readFileSync(file).subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])));
  };
  const denied = async operation => { try { await operation();return false; } catch { return true; } };
  const root = path.join(context.fixtures,'python-demo');
  const movedRoot = path.join(context.fixtures,'moved-python-demo');
  const original = path.join(root,'main.py');
  const renamed = path.join(root,'moved.py');
  const baseline = fs.readFileSync(original);
  const digest = value => crypto.createHash('sha256').update(value).digest('hex');
  let api, listener;
  save();
  try {
    check('Real Linux extension host',process.platform==='linux');
    check('Expected VS Code build',vscode.version==='1.143.0');
    check('Workspace trust enabled',vscode.workspace.getConfiguration('security.workspace.trust').get('enabled')===true);
    const expectedWorkspace=phase==='untrusted-after'?path.join(session,'untrusted','Untrusted.code-workspace'):path.join(context.state,'Atlas.code-workspace');
    check('Exact isolated workspace opened',vscode.workspace.workspaceFile.fsPath===expectedWorkspace);
    const extension=vscode.extensions.getExtension('TheOutlandsDev.code-atlas');
    if(phase.startsWith('untrusted-')){
      check('Generated control workspace remains untrusted',vscode.workspace.isTrusted===false);
      check('Published extension stays inactive in Restricted Mode',!extension||!extension.isActive);
      report.status='PASS';save();return;
    }
    check('Only explicitly provisioned fixture workspace is trusted',vscode.workspace.isTrusted===true);
    check('Published extension registered',Boolean(extension));
    check('Published extension version',extension.packageJSON.version==='0.1.0');
    check('Installed VSIX rather than source development build',extension.extensionPath.startsWith(path.join(context.state,'vscode-extensions')+path.sep));
    api=await extension.activate();
    check('Actual extension activated',extension.isActive&&api&&typeof api.getCatalog==='function');
    if(phase==='first'){
      await vscode.workspace.getConfiguration('editor').update('fontSize',16,vscode.ConfigurationTarget.Global);
      check('Isolated editor setting written',vscode.workspace.getConfiguration('editor').get('fontSize')===16);
    }else{
      check('Isolated editor setting persisted across restart',vscode.workspace.getConfiguration('editor').get('fontSize')===16);
      const prior=JSON.parse(fs.readFileSync(path.join(session,'native-first.json')));
      check('Catalog identity persisted across restart',JSON.stringify(api.getCatalog().projects.map(p=>p.id).sort())===JSON.stringify(prior.projectIds));
    }
    const scan=await vscode.commands.executeCommand('codeAtlas.refresh');
    check('Actual scanner completed',scan&&scan.status==='PASS');
    const catalog=api.getCatalog();
    const expectedRoots=new Set([context.fixtures,...['python-demo','rust-demo','typescript-demo'].map(name=>path.join(context.fixtures,name))]);
    check('Only the explicit fixture base and three generated projects cataloged',catalog.projects.length===expectedRoots.size&&catalog.projects.every(p=>expectedRoots.has(p.rootPath)));
    const python=catalog.projects.find(p=>p.rootPath===root);
    check('Python fixture discovered',Boolean(python));
    check('Rust fixture discovered',catalog.projects.some(p=>p.languages.includes('Rust')));
    check('TypeScript fixture discovered',catalog.projects.some(p=>p.languages.includes('TypeScript')));
    check('No test workspaces configured',catalog.projects.every(p=>p.testStatus==='NOT_CONFIGURED'));
    const panel=await vscode.commands.executeCommand('codeAtlas.openMap');
    check('Native webview panel created',panel&&panel.webview&&typeof panel.webview.html==='string');
    panel.reveal(vscode.ViewColumn.One);
    await capture('map');
    check('Native source selection command',await vscode.commands.executeCommand('codeAtlas.openProject',python.id,'Python')===true);
    check('Native file-open command',await vscode.commands.executeCommand('codeAtlas.openFile',python.id,'main.py')===true);
    const uri=api.provider.uri(python.id,'main.py');
    const document=await vscode.workspace.openTextDocument(uri);
    check('Native document uses read-only scheme',document.uri.scheme==='code-atlas');
    check('Native document contains fixture bytes',document.getText()===baseline.toString('utf8'));
    await capture('readonly-source');
    check('File-system registration is read-only',vscode.workspace.isWritableFileSystem('code-atlas')===false);
    check('Native stat advertises read-only',(await vscode.workspace.fs.stat(uri)).permissions===vscode.FilePermission.Readonly);
    check('Native file-system write denied',await denied(()=>vscode.workspace.fs.writeFile(uri,Buffer.from('unexpected write\n'))));
    check('Write attempt preserved fixture',digest(fs.readFileSync(original))===digest(baseline));
    check('Native file-system delete denied',await denied(()=>vscode.workspace.fs.delete(uri)));
    const renameUri=api.provider.uri(python.id,'provider-renamed.py');
    check('Native file-system rename denied',await denied(()=>vscode.workspace.fs.rename(uri,renameUri)));
    check('Traversal request denied',await vscode.commands.executeCommand('codeAtlas.openFile',python.id,'../outside.py')===false);
    const events=[];
    listener=api.provider.onDidChangeFile(values=>events.push(...values));
    fs.renameSync(original,renamed);
    for(let attempt=0;attempt<30&&!events.some(e=>e.uri.toString()===uri.toString()&&e.type===vscode.FileChangeType.Deleted);attempt+=1) await pause(200);
    check('Open-file watcher reported renamed path missing',events.some(e=>e.uri.toString()===uri.toString()&&e.type===vscode.FileChangeType.Deleted));
    check('Moved-from URI denied by native file API',await denied(()=>vscode.workspace.fs.readFile(uri)));
    check('Moved-to file opens through native command',await vscode.commands.executeCommand('codeAtlas.openFile',python.id,'moved.py')===true);
    fs.renameSync(renamed,original);
    fs.renameSync(root,movedRoot);
    const movedScan=await vscode.commands.executeCommand('codeAtlas.refresh');
    check('Scanner refreshed after source-root move',movedScan&&movedScan.status==='PASS');
    const moved=api.getCatalog().projects.find(p=>p.rootPath===movedRoot);
    check('Moved source root cataloged with new identity',moved&&moved.id!==python.id&&!api.getCatalog().projects.some(p=>p.id===python.id));
    check('Stale project URI denied',await denied(()=>vscode.workspace.fs.readFile(uri)));
    check('Moved source root opens read-only',await vscode.commands.executeCommand('codeAtlas.openFile',moved.id,'main.py')===true);
    const movedUri=api.provider.uri(moved.id,'main.py');
    fs.unlinkSync(path.join(movedRoot,'main.py'));
    check('Deleted fixture denied by native file API',await denied(()=>vscode.workspace.fs.readFile(movedUri)));
    fs.writeFileSync(path.join(movedRoot,'main.py'),baseline,{mode:0o600});
    fs.renameSync(movedRoot,root);
    const restored=await vscode.commands.executeCommand('codeAtlas.refresh');
    check('Fixture scan restored',restored&&restored.status==='PASS');
    const expected=JSON.parse(fs.readFileSync(path.join(session,'fixture-baseline.json'),'utf8'));
    const actual={};
    function visit(directory){for(const item of fs.readdirSync(directory,{withFileTypes:true})){const full=path.join(directory,item.name);assert.ok(!item.isSymbolicLink());if(item.isDirectory())visit(full);else actual[path.relative(context.fixtures,full)]=digest(fs.readFileSync(full));}}
    visit(context.fixtures);
    check('Disposable fixture bytes restored after controlled mutations',JSON.stringify(Object.entries(actual).sort())===JSON.stringify(Object.entries(expected).sort()));
    report.projectIds=api.getCatalog().projects.map(p=>p.id).sort();
    report.status='PASS';save();
  } catch(error) {
    if(report.status!=='BLOCKED_WORKSPACE_TRUST')report.status='FAIL';
    report.errorType=String(error&&error.name||'Error');save();throw error;
  } finally {
    listener?.dispose();
    // Only explicitly created disposable files are restored. No real projects are touched.
    if(fs.existsSync(movedRoot)&&!fs.existsSync(root))fs.renameSync(movedRoot,root);
    if(fs.existsSync(renamed)&&!fs.existsSync(original))fs.renameSync(renamed,original);
    if(fs.existsSync(root))fs.writeFileSync(original,baseline,{mode:0o600});
    try {if(api)await api.scan();}catch{}
  }
};
