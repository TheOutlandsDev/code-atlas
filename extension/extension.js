'use strict';
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {ROOT,loadPolicy,relative,canonical} = require('./policy');
const {ReadonlyProvider,SCHEME} = require('./readonly');
const {SourceTree} = require('./tree');
const {Scanner} = require('./scanner');
const {ReviewedTests} = require('./reviewed');
const {readCatalog,emptyCatalog,CATALOG_FILE} = require('./catalog');
const WORKSPACE = ROOT+'/Atlas.code-workspace';
const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join('|') === [...keys].sort().join('|');
function activate(context) {
  let policy = loadPolicy(); let catalog = emptyCatalog(); let projects = new Map(); let panel; let disposed = false;
  const output = vscode.window.createOutputChannel('Code Atlas');
  const status = value => output.appendLine('Code Atlas: '+value);
  const reviewed = new ReviewedTests(vscode,state => { if(panel)void panel.webview.postMessage({type:'reviewedTests',state}); },status);
  const runAllReviewedTests = () => reviewed.run();
  const provider = new ReadonlyProvider(vscode,policy,() => projects,() => !disposed && vscode.workspace.isTrusted);
  const tree = new SourceTree(vscode,provider,() => projects);
  const treeView = vscode.window.createTreeView('codeAtlas.sources',{treeDataProvider:tree,showCollapseAll:true});
  const refreshCatalog = () => {
    const nextPolicy = loadPolicy();
    const next = readCatalog(nextPolicy);
    const nextProjects = new Map(next.projects.map(p => [p.id,p]));
    // All validation completes before this synchronous commit. A rejected policy/catalog leaves the prior pair intact.
    policy = nextPolicy; provider.policy = nextPolicy; catalog = next; projects = nextProjects;
    provider.reconcile(); tree.refresh(); if (panel) void panel.webview.postMessage({type:'catalog',catalog}); status('CATALOG_UPDATED'); return next;
  };
  try { refreshCatalog(); } catch { status('CATALOG_NOT_READY'); }
  const scanner = new Scanner(refreshCatalog,status,context.extensionPath);
  const scan = () => !disposed && vscode.workspace.isTrusted ? scanner.request() : Promise.resolve({status:'DENIED'});
  const project = id => { if (typeof id !== 'string' || !/^p-[0-9a-f]{16}$/.test(id) || !projects.has(id)) throw new Error('Unknown source ID'); return projects.get(id); };
  const openProject = async (id,preferredLanguage) => {
    if (disposed || !vscode.workspace.isTrusted) throw new Error('Trusted source navigation required');
    const p = project(id); policy.authorizeRoot(p.rootPath); if (p.status !== 'READ_ONLY_SOURCE') throw new Error('Source root unavailable');
    const languages = p.languages.length ? p.languages : [p.primaryLanguage || 'Unclassified'];
    if (preferredLanguage !== undefined && (typeof preferredLanguage !== 'string' || !languages.includes(preferredLanguage))) throw new Error('Unsupported project language');
    const language = preferredLanguage === undefined ? (languages.includes(p.primaryLanguage) ? p.primaryLanguage : languages[0]) : preferredLanguage;
    await vscode.commands.executeCommand('codeAtlas.sources.focus');
    await treeView.reveal(tree.projectNode(id,language),{select:true,focus:true,expand:1});
    return true;
  };
  const openFile = async (id,rel) => {
    if (disposed || !vscode.workspace.isTrusted) throw new Error('Trusted source navigation required');
    const p = project(id); relative(rel); policy.resolve(p.rootPath,rel,false);
    const uri = provider.uri(id,rel); const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document,{preview:false}); provider.watchOpen(uri); return true;
  };
  const fixedOpen = async target => {
    if (disposed || !vscode.workspace.isTrusted) return false;
    canonical(target,false);
    await vscode.commands.executeCommand('vscode.openFolder',vscode.Uri.file(target),{forceNewWindow:true});
    return true;
  };
  const openTests = id => { const p = project(id); const target = policy.reviewedTests.get(p.rootPath); if (p.testStatus !== 'REVIEWED_ISOLATED_TESTS' || !target) throw new Error('No reviewed test workspace'); return fixedOpen(target.workspace); };
  const message = async value => {
    try {
      if (exactKeys(value,['type']) && value.type === 'runAllReviewedTests') return await runAllReviewedTests();
      if (exactKeys(value,['type']) && value.type === 'refresh') return await scan();
      if (exactKeys(value,['type','id']) && value.type === 'openProject') return await openProject(value.id);
      if (exactKeys(value,['type','id','language']) && value.type === 'openProject') {
        if (typeof value.language !== 'string') throw new Error('Project language required');
        return await openProject(value.id,value.language);
      }
      if (exactKeys(value,['type','id']) && value.type === 'openTests') return await openTests(value.id);
      if (exactKeys(value,['type','id','relativePath']) && value.type === 'openFile') return await openFile(value.id,value.relativePath);
      status('MESSAGE_REJECTED'); return false;
    } catch { status('NAVIGATION_DENIED'); return false; }
  };
  const openMap = () => {
    if (panel) { panel.reveal(vscode.ViewColumn.One); return panel; }
    const media = vscode.Uri.joinPath(context.extensionUri,'extension/media');
    panel = vscode.window.createWebviewPanel('codeAtlasMap','Code Atlas',vscode.ViewColumn.One,{enableScripts:true,enableForms:false,enableCommandUris:false,localResourceRoots:[media],retainContextWhenHidden:true});
    const current = panel; const nonce = crypto.randomBytes(24).toString('hex');
    const tokens = {
      '{{CSP}}': "default-src 'none'; img-src "+current.webview.cspSource+" data:; style-src "+current.webview.cspSource+"; script-src 'nonce-"+nonce+"'; connect-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none';",
      '{{NONCE}}':nonce,
      '{{STYLE_URI}}':current.webview.asWebviewUri(vscode.Uri.joinPath(media,'styles.css')).toString(),
      '{{SCRIPT_URI}}':current.webview.asWebviewUri(vscode.Uri.joinPath(media,'app.js')).toString(),
      '{{INITIAL_REVIEWED_TESTS}}':JSON.stringify(reviewed.state()).replace(/</g,'\\u003c').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029'),
      '{{INITIAL_CATALOG}}':JSON.stringify(catalog).replace(/</g,'\\u003c').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029')
    };
    const template = fs.readFileSync(path.join(context.extensionPath,'extension/media/index.template.html'),'utf8');
    current.webview.html = template.replace(/\{\{(?:CSP|NONCE|STYLE_URI|SCRIPT_URI|INITIAL_CATALOG|INITIAL_REVIEWED_TESTS)\}\}/g,token => tokens[token]);
    context.subscriptions.push(current.webview.onDidReceiveMessage(value => { void message(value); }),current.onDidDispose(() => { if (panel === current) panel = undefined; }));
    return current;
  };
  const command = (id,handler) => context.subscriptions.push(vscode.commands.registerCommand(id,async (...args) => { try { return await handler(...args); } catch { status('COMMAND_DENIED'); return false; } }));
  command('codeAtlas.openMap',() => openMap());
  command('codeAtlas.refresh',() => scan());
  command('codeAtlas.runAllReviewedTests',() => runAllReviewedTests());
  command('codeAtlas.openWorkspace',() => fixedOpen(WORKSPACE));
  command('codeAtlas.openProject',(id,language) => openProject(id,language));
  command('codeAtlas.openFile',(id,rel) => openFile(id,rel));
  command('codeAtlas.openTests',id => openTests(id));
  command('codeAtlas.openTreeTests',node => openTests(tree.reviewedProjectId(node)));
  context.subscriptions.push(output,provider,tree,treeView,scanner,reviewed,vscode.workspace.registerFileSystemProvider(SCHEME,provider,{isCaseSensitive:true,isReadonly:true}),vscode.workspace.onDidOpenTextDocument(document => { provider.watchOpen(document.uri); }),vscode.workspace.onDidCloseTextDocument(document => { if (document.uri.scheme === SCHEME) provider.unwatch(document.uri); }));
  for (const document of vscode.workspace.textDocuments) provider.watchOpen(document.uri);
  const catalogListener = () => { try { refreshCatalog(); } catch { status('CATALOG_UPDATE_REJECTED'); } };
  fs.watchFile(CATALOG_FILE,{interval:1000,persistent:false},catalogListener);
  context.subscriptions.push({dispose:() => fs.unwatchFile(CATALOG_FILE,catalogListener)});
  const ownWindow = () => vscode.workspace.workspaceFile && vscode.workspace.workspaceFile.scheme === 'file' && vscode.workspace.workspaceFile.fsPath === WORKSPACE;
  let interval;
  if (ownWindow() && vscode.workspace.isTrusted) {
    openMap(); if(policy.bases.length)void scan(); interval = setInterval(() => { if (ownWindow()) void scan(); },60000); interval.unref?.();
  }
  context.subscriptions.push({dispose(){ disposed = true; if (interval) clearInterval(interval); if (panel) panel.dispose(); }});
  return {provider,tree,scanner,scan,getCatalog:() => catalog,refreshCatalog,openMap,openProject,openFile,openTests,runAllReviewedTests,getReviewedTestsState:()=>reviewed.state(),receiveMessage:message};
}
function deactivate() {}
module.exports = {activate,deactivate,WORKSPACE};
