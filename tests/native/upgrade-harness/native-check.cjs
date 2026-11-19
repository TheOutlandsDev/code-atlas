'use strict';
// Original synthetic native checks. Copyright 2026 TheOutlandsDev. MIT.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vscode = require('vscode');

exports.run = async function run() {
  const session = process.env.ATLAS_UPGRADE_SESSION;
  const phase = process.env.ATLAS_UPGRADE_PHASE;
  const state = path.join(session, 'state');
  const root = path.join(session, 'fixtures', 'orchard');
  const expectedVersion = ['untrusted', 'baseline'].includes(phase) ? '0.1.2' : '0.1.3';
  const report = {phase, status: 'RUNNING', checks: []};
  const file = path.join(session, phase + '.json');
  const save = () => fs.writeFileSync(file, JSON.stringify(report, null, 2) + '\n', {mode: 0o600});
  const check = (name, condition) => {
    report.failedCheck = name;
    assert.ok(condition, name);
    delete report.failedCheck;
    report.checks.push(name);
    save();
  };
  try {
    check('Pinned Linux VS Code 1.143.0', process.platform === 'linux' && vscode.version === '1.143.0');
    check('Workspace trust enabled', vscode.workspace.getConfiguration('security.workspace.trust').get('enabled') === true);
    check('Exact generated workspace file', vscode.workspace.workspaceFile.fsPath === path.join(state, 'Atlas.code-workspace'));
    const extension = vscode.extensions.getExtension('TheOutlandsDev.code-atlas');
    if (phase === 'untrusted') {
      check('Generated workspace begins untrusted', vscode.workspace.isTrusted === false);
      check('Code Atlas stays inactive in Restricted Mode', !extension || !extension.isActive);
    } else {
      check('Expected VSIX registered', extension?.packageJSON.version === expectedVersion);
      check('Generated workspace remains trusted', vscode.workspace.isTrusted === true);
      check('Extension loads from the isolated VSIX directory', extension.extensionPath.startsWith(path.join(state, 'vscode-extensions') + path.sep));
      const api = await extension.activate();
      check('Installed Code Atlas activated', extension.isActive && typeof api?.getCatalog === 'function');
      report.installedVersion = extension.packageJSON.version;
      if (phase === 'baseline') {
        await vscode.workspace.getConfiguration('editor').update('fontSize', 17, vscode.ConfigurationTarget.Global);
      }
      check('Disposable editor setting retained', vscode.workspace.getConfiguration('editor').get('fontSize') === 17);
      if (phase !== 'baseline') {
        const previousPhase = phase === 'upgraded' ? 'baseline' : 'upgraded';
        const prior = JSON.parse(fs.readFileSync(path.join(session, previousPhase + '.json')));
        const current = api.getCatalog();
        check('Saved catalog available on activation', current.projects.some(project => project.id === prior.projectId));
      }
      const scan = await vscode.commands.executeCommand('codeAtlas.refresh');
      check('Native Code Atlas scan completed', scan?.status === 'PASS');
      const catalog = api.getCatalog();
      const project = catalog.projects.find(item => item.rootPath === root);
      check('Exactly one configured synthetic root cataloged', catalog.projects.length === 1 && project?.scanComplete === true);
      check('No project tests are configured', project.testStatus === 'NOT_CONFIGURED');
      const expected = {
        'legacy.PY': 'Custom Python',
        'main.py': 'Python',
        'pyproject.toml': 'TOML',
      };
      if (phase !== 'baseline') {
        expected['mixed.pY'] = 'Python';
        expected['settings.JsOn'] = 'JSON';
      }
      const indexed = Object.fromEntries(project.sampleFiles.map(row => [row.relativePath, row.language]));
      report.indexed = indexed;
      report.generation = catalog.generation;
      report.projectId = project.id;
      const indexedMatches = Object.keys(indexed).length === Object.keys(expected).length &&
        Object.entries(expected).every(([name, language]) => indexed[name] === language);
      check('Catalog inventory and language mappings match', indexedMatches);
      check('Extension resolves exact custom .PY before lowercase fallback', api.provider.policy.language('legacy.PY') === 'Custom Python');
      check('Excluded dependency control stays out of the catalog', indexed['node_modules/ignored.pY'] === undefined);
      if (phase !== 'baseline') {
        const previousPhase = phase === 'upgraded' ? 'baseline' : 'upgraded';
        const previous = JSON.parse(fs.readFileSync(path.join(session, previousPhase + '.json')));
        check('Stable project identity on the same synthetic root', project.id === previous.projectId);
        check('Catalog generation advances on fresh scan', Number(catalog.generation) > Number(previous.generation));
      }
      check('Atlas file provider advertises read-only access', vscode.workspace.fs.isWritableFileSystem('code-atlas') === false);
      for (const name of Object.keys(expected)) {
        const uri = api.provider.uri(project.id, name);
        const opened = await vscode.commands.executeCommand('codeAtlas.openFile', project.id, name);
        const bytes = await vscode.workspace.fs.readFile(uri);
        check('Read-only open matches fixture bytes for ' + name, opened === true &&
          Buffer.from(bytes).equals(fs.readFileSync(path.join(root, name))) &&
          (await vscode.workspace.fs.stat(uri)).permissions === vscode.FilePermission.Readonly);
      }
    }
    report.status = 'PASS';
  } catch (error) {
    report.status = 'FAIL';
    throw error;
  } finally {
    save();
  }
};
