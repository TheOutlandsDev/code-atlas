'use strict';
// Offline DOM-contract tests. No browser, network, project file, or VS Code process is opened.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');
const template = fs.readFileSync(path.join(__dirname, 'index.template.html'), 'utf8');
class Node {
  constructor(tag) {this.tagName = tag; this.children = []; this.attrs = {}; this.events = new Map(); this.className = ''; this.value = ''; this.hidden = false; this._text = ''; this.classList = {add: value => {this.className += ' ' + value;}, remove: value => {this.className = this.className.split(' ').filter(item => item !== value).join(' ');}};}
  set textContent(value) {this._text = String(value); this.children = [];}
  get textContent() {return this._text + this.children.map(child => child.textContent).join('');}
  get firstChild() {return this.children[0];}
  setAttribute(key, value) {this.attrs[key] = String(value);}
  append(...children) {children.forEach(child => {child.parent = this; this.children.push(child);});}
  replaceChildren(...children) {this.children = []; this._text = ''; this.append(...children);}
  addEventListener(type, handler) {if (!this.events.has(type)) this.events.set(type, []); this.events.get(type).push(handler);}
  fire(type, data = {}) {const event = {target: this, preventDefault() {}, stopPropagation() {}, ...data}; (this.events.get(type) || []).forEach(handler => handler(event));}
  setPointerCapture() {}
  getBoundingClientRect() {return {width: 1120, height: 740};}
  closest(selector) {return selector === '.node' && (this.attrs.class || this.className).split(' ').includes('node') ? this : this.parent?.closest(selector);}
}
const project = (id, extras = {}) => ({id: 'p-' + id.repeat(16), label: 'Project ' + id, rootPath: '/configured/code/' + id, languages: ['Rust'], primaryLanguage: 'Rust', fileCount: 4, status: 'READ_ONLY_SOURCE', scanComplete: true, sourceFingerprint: id, sampleFiles: [{relativePath: 'src/lib.rs', language: 'Rust'}], validation: {status: 'SYNTAX_OK', syntaxPassed: 4, syntaxErrors: 0, pending: 0, unsupported: 0}, testStatus: 'NOT_CONFIGURED', isolatedCopyState: 'NOT_CONFIGURED', ...extras});
const fixture = () => ({schemaVersion: 1, generation: 1, generatedAtUtc: '2026-10-22T12:00:00Z', coverage: {projectCount: 4, codeFiles: 16, complete: false, limited: true, excludedDirectories: 12, unreadableDirectories: 1, scanBudgetExceeded: false}, validation: {mode: 'static_only', pending: 2}, projects: [project('a', {label: '<img src=x onerror=alert(1)>', testStatus: 'REVIEWED_ISOLATED_TESTS', isolatedCopyState: 'SOURCE_CHANGED'}), project('b', {languages: ['Python', 'Shell'], primaryLanguage: 'Python', validation: {status: 'STALE', syntaxPassed: 0, syntaxErrors: 0, pending: 2, unsupported: 0}}), project('c', {scanComplete: false}), project('d', {status: 'UNREADABLE', scanComplete: false})]});
function descendants(node) {return node.children.flatMap(child => [child, ...descendants(child)]);}
function boot(catalog = fixture(), reviewed = {available:true,running:false,latest:null}) {
  const ids = [...template.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  const elements = new Map(ids.map(id => [id, new Node('div')])); const messages = []; const events = new Map();
  const document = {getElementById(id) {assert.ok(elements.has(id), 'Unknown DOM id ' + id); return elements.get(id);}, createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag)};
  const window = {INITIAL_CATALOG: catalog, INITIAL_REVIEWED_TESTS:reviewed, addEventListener(type, handler) {events.set(type, handler);}};
  const context = vm.createContext({document, window, acquireVsCodeApi: () => ({postMessage: value => messages.push(JSON.parse(JSON.stringify(value)))}), setTimeout: () => 1, clearTimeout() {}, console});
  vm.runInContext(source, context, {filename: 'live-atlas-app.js', timeout: 1000});
  return {get: id => elements.get(id), messages, reviewed(value){events.get('message')({data:{type:'reviewedTests',state:value}});}, catalog(value) {events.get('message')({data: {type: 'catalog', catalog: value}});}, find(node, text) {return descendants(node).find(child => child.tagName === 'button' && child.textContent === text);}};
}
test('initial catalog renders primary-language network, exact counts, and partial coverage', () => {
  const ui = boot(); assert.equal(ui.get('project-total').textContent, '4'); assert.equal(ui.get('file-total').textContent, '16');
  assert.equal(ui.get('language-total').textContent, '3'); assert.equal(ui.get('covered-count').textContent, '2'); assert.equal(ui.get('limited-count').textContent, '2');
  assert.equal(ui.get('stale-count').textContent, '1'); assert.equal(ui.get('excluded-count').textContent, '12'); assert.match(ui.get('coverage-note').textContent, /partial/);
  assert.match(ui.get('shown-count').textContent, /2 primary language groups/); assert.equal(ui.messages.length, 0);
  assert.match(ui.get('updated').textContent, /open-file refresh 1s/); assert.doesNotMatch(ui.get('updated').textContent, /open-file checks/);
});
test('untrusted labels remain text nodes; dynamic markup APIs and execution APIs are absent', () => {
  const ui = boot(); assert.match(ui.get('projects').textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(descendants(ui.get('projects')).some(node => node.tagName === 'img'), false);
  assert.doesNotMatch(source, /innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new\s+Function|\bfetch\s*\(|XMLHttpRequest|WebSocket|import\s*\(/);
});
test('refresh posts only the exact refresh request', () => {
  const ui = boot(); ui.get('refresh').fire('click'); assert.deepEqual(ui.messages, [{type: 'refresh'}]);
});
test('project and sampled source actions use exact allowlisted message shapes', () => {
  const ui = boot(); ui.get('projects').children[0].fire('click');
  ui.find(ui.get('details'), 'Browse source files ↗').fire('click'); ui.find(ui.get('details'), 'src/lib.rs').fire('click');
  assert.deepEqual(ui.messages, [{type: 'openProject', id: 'p-aaaaaaaaaaaaaaaa', language: 'Rust'}, {type: 'openFile', id: 'p-aaaaaaaaaaaaaaaa', relativePath: 'src/lib.rs'}]);
});
test('secondary language selection survives source browsing and options report counts', () => {
  const ui = boot(); ui.get('language').value = 'Shell'; ui.get('language').fire('change');
  assert.equal(ui.get('projects').children.length, 1); ui.get('projects').children[0].fire('click');
  ui.find(ui.get('details'), 'Browse source files ↗').fire('click');
  assert.deepEqual(ui.messages, [{type: 'openProject', id: 'p-bbbbbbbbbbbbbbbb', language: 'Shell'}]);
  assert.ok(ui.get('language').children.some(option => option.value === 'Shell' && option.textContent === 'Shell (1)'));
});
test('reviewed test shortcuts remain available when their parent has no selected language', () => {
  const data = fixture(); data.projects[0].languages = ['TOML']; data.projects[0].primaryLanguage = 'TOML';
  const ui = boot(data); ui.get('language').value = 'Rust'; ui.get('language').fire('change');
  assert.equal(ui.get('test-ready-count').textContent, '1');
  assert.match(ui.get('test-shortcuts').textContent, /separately reviewed/);
  ui.get('test-shortcuts').children[0].fire('click');
  assert.deepEqual(ui.messages, [{type: 'openTests', id: 'p-aaaaaaaaaaaaaaaa'}]);
  const updated = fixture(); updated.projects[0].testStatus = 'NOT_CONFIGURED'; ui.catalog(updated);
  assert.equal(ui.get('test-ready-count').textContent, '0'); assert.match(ui.get('test-shortcuts').textContent, /No reviewed test workspace/);
});
test('reviewed test action only opens its fixed-ID workspace; stale copy has explicit warning', () => {
  const ui = boot(); ui.get('projects').children[0].fire('click');
  assert.match(ui.get('details').textContent, /copy freshness/);
  ui.find(ui.get('details'), 'Open test workspace ↗').fire('click'); assert.deepEqual(ui.messages, [{type: 'openTests', id: 'p-aaaaaaaaaaaaaaaa'}]);
  ui.get('projects').children[1].fire('click'); assert.equal(ui.find(ui.get('details'), 'Open test workspace ↗'), undefined);
  assert.match(ui.get('details').textContent, /Test and runtime setup is not configured/);
});
test('relative source input rejects traversal, absolute paths, empty components and backslashes', () => {
  const ui = boot(); ui.get('projects').children[0].fire('click'); const group = descendants(ui.get('details')).find(node => node.className === 'file-open'); const input = group.children[0];
  for (const value of ['../secret', '/etc/passwd', 'src/../secret', 'src//file.rs', 'src\\file.rs', './src/lib.rs']) {input.value = value; group.children[1].fire('click');}
  assert.equal(ui.messages.length, 0); input.value = 'src/new_test.rs'; input.fire('keydown', {key: 'Enter'});
  assert.deepEqual(ui.messages, [{type: 'openFile', id: 'p-aaaaaaaaaaaaaaaa', relativePath: 'src/new_test.rs'}]);
});
test('missing or unreadable roots cannot emit source-open requests', () => {
  const ui = boot(); ui.get('projects').children[3].fire('click');
  ui.find(ui.get('details'), 'Browse source files ↗').fire('click'); ui.find(ui.get('details'), 'src/lib.rs').fire('click'); assert.deepEqual(ui.messages, []);
});
test('search, secondary language membership and coverage filters remain metadata-only', () => {
  const ui = boot(); ui.get('search').value = 'src/lib.rs'; ui.get('search').fire('input'); assert.equal(ui.get('results-count').textContent, '4');
  ui.get('language').value = 'Shell'; ui.get('language').fire('change'); assert.equal(ui.get('results-count').textContent, '1'); assert.equal(ui.get('map-title').textContent, 'Shell source roots');
  ui.get('clear').fire('click'); ui.get('coverage-filter').value = 'stale'; ui.get('coverage-filter').fire('change'); assert.equal(ui.get('results-count').textContent, '1'); assert.deepEqual(ui.messages, []);
});
test('catalog update refreshes counts and removes stale selections without emitting actions', () => {
  const ui = boot(); ui.get('projects').children[0].fire('click'); const next = fixture(); next.generation = 2; next.projects = [project('b')]; next.coverage.codeFiles = 4;
  ui.catalog(next); assert.equal(ui.get('project-total').textContent, '1'); assert.equal(ui.get('detail-title').textContent, 'Choose a project'); assert.equal(ui.messages.length, 0);
  ui.catalog({schemaVersion: 99, projects: []}); assert.equal(ui.get('project-total').textContent, '1');
});
test('malformed, duplicate IDs and traversal samples are rejected before rendering', () => {
  const data = fixture(); data.projects.push(project('a')); data.projects.push({...project('a'), id: 'arbitrary-id'}); data.projects[0].sampleFiles.push({relativePath: '../../secret', language: 'Rust'});
  const ui = boot(data); assert.equal(ui.get('project-total').textContent, '4'); ui.get('projects').children[0].fire('click');
  assert.equal(ui.find(ui.get('details'), '../../secret'), undefined);
});
test('map zoom, reset and keyboard pan operate locally without messages', () => {
  const ui = boot(); ui.get('zoom-in').fire('click'); assert.equal(ui.get('zoom-label').textContent, '115%'); ui.get('reset').fire('click'); assert.equal(ui.get('zoom-label').textContent, '100%');
  ui.get('viewport').fire('keydown', {key: 'ArrowLeft'}); assert.match(ui.get('scene').attrs.transform, /translate\(25 0\)/); assert.deepEqual(ui.messages, []);
});
test('large language views label their drawing limit while retaining every source-list entry', () => {
  const data = fixture(); data.projects = Array.from({length: 40}, (_, index) => ({...project('a'), id: 'p-' + index.toString(16).padStart(16, '0'), label: 'Rust project ' + index}));
  const ui = boot(data); ui.get('language').value = 'Rust'; ui.get('language').fire('change');
  assert.match(ui.get('shown-count').textContent, /First 24 of 40/); assert.equal(ui.get('projects').children.length, 40);
  assert.equal(ui.get('nodes').children.filter(node => (node.attrs.class || '').includes('project-node')).length, 24);
});
test('configured base receipts display limits and path metadata as text', () => {
  const data = fixture(); data.coverage.bases = [{path: '/configured/code', status: 'LIMITED', visitedDirectories: 42, projects: 4, limitsHit: ['directory budget']}];
  const ui = boot(data); assert.match(ui.get('coverage-bases').textContent, /\/configured\/code/); assert.match(ui.get('coverage-bases').textContent, /directory budget/);
});
test('a live catalog update preserves an unfinished relative source-path draft', () => {
  const ui = boot(); ui.get('projects').children[0].fire('click');
  let group = descendants(ui.get('details')).find(node => node.className === 'file-open'); group.children[0].value = 'src/unfinished'; group.children[0].fire('input');
  ui.catalog(fixture()); group = descendants(ui.get('details')).find(node => node.className === 'file-open'); assert.equal(group.children[0].value, 'src/unfinished');
});
test('template uses fixed local-resource tokens and nonced initialization only', () => {
  for (const token of ['{{CSP}}', '{{NONCE}}', '{{STYLE_URI}}', '{{SCRIPT_URI}}', '{{INITIAL_CATALOG}}']) assert.ok(template.includes(token), token);
  assert.doesNotMatch(template, /https?:|\son(?:click|load|error)=|<iframe|<form/i);
  assert.equal((template.match(/<script /g) || []).length, 2); assert.equal((template.match(/<script nonce="\{\{NONCE\}\}"/g) || []).length, 2);
});


test('five reviewed workspace shortcuts include Example Control after language filtering', () => {
  const names=['Example Rust','Example Native','Example Python','Example Service','Example Control'];
  const data=fixture();data.projects=names.map((label,index)=>project(String.fromCharCode(97+index),{label,languages:['Python'],primaryLanguage:'Python',testStatus:'REVIEWED_ISOLATED_TESTS',isolatedCopyState:'BASELINE_CURRENT'}));
  const ui=boot(data);ui.get('language').value='Rust';ui.get('language').fire('change');
  assert.equal(ui.get('test-ready-count').textContent,'5');assert.equal(ui.get('test-shortcuts').children.length,5);
  const shortcut=ui.get('test-shortcuts').children.find(node=>node.textContent.includes('Example Control'));assert.ok(shortcut);shortcut.fire('click');
  assert.deepEqual(ui.messages,[{type:'openTests',id:'p-eeeeeeeeeeeeeeee'}]);
});


test('manual Run all button sends one exact type-only request and disables while active',()=>{const ui=boot();assert.equal(ui.get('run-all-reviewed').disabled,false);ui.get('run-all-reviewed').fire('click');ui.get('run-all-reviewed').fire('click');assert.deepEqual(ui.messages,[{type:'runAllReviewedTests'}]);assert.equal(ui.get('run-all-reviewed').disabled,true);ui.get('refresh').fire('click');assert.deepEqual(ui.messages[1],{type:'refresh'});});
test('aggregate state shows derived results duration and coverage as safe text',()=>{const ui=boot();ui.reviewed({available:true,running:true,progress:'Example 1/8',latest:null});assert.equal(ui.get('run-all-reviewed').disabled,true);assert.match(ui.get('reviewed-run-status').textContent,/Example/);ui.reviewed({available:true,running:false,latest:{status:'PASS',testsPassed:3,syntaxChecksPassed:2,durationMs:1234,originalFilesVerified:2,coverage:[{project:'<img>',percentage:85.591,gate:80}],reportText:'/fixed/RESULTS.txt'}});assert.equal(ui.get('run-all-reviewed').disabled,false);assert.match(ui.get('reviewed-run-status').textContent,/3 tests passed.*2 syntax.*1.2s.*2 originals.*<img> coverage 85.59%/);assert.equal(descendants(ui.get('reviewed-run-status')).length,0);assert.deepEqual(ui.messages,[]);});
test('Run all remains unavailable in non-Live windows and language filters never start tests',()=>{const ui=boot(fixture(),{available:false,running:false,latest:null});ui.get('run-all-reviewed').fire('click');ui.get('language').value='Rust';ui.get('language').fire('change');ui.catalog(fixture());assert.equal(ui.get('run-all-reviewed').disabled,true);assert.deepEqual(ui.messages,[]);});
test('malformed aggregate messages cannot re-enable or inject report actions',()=>{const ui=boot();ui.get('run-all-reviewed').fire('click');ui.reviewed({available:'true',running:false});assert.equal(ui.get('run-all-reviewed').disabled,true);ui.reviewed({available:true,running:false,latest:{status:'RUN rm secret',reportText:'javascript:evil'}});assert.doesNotMatch(ui.get('reviewed-run-status').textContent,/rm secret|javascript/);assert.deepEqual(ui.messages,[{type:'runAllReviewedTests'}]);});
