'use strict';
(() => {
  const bridge = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : undefined;
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = ['#40def0', '#60a5fa', '#b79aff', '#6cddb4', '#f3bf68', '#ff9cba', '#8bc8e9'];
  const state = {catalog: null, projects: [], selected: null, fileDraft: '', search: '', language: '', coverage: '', zoom: 1, x: 0, y: 0};
  let noticeTimer, pointer; let reviewedRunning=false; let reviewedAvailable=false;
  const clean = (value, max = 240) => typeof value === 'string' ? value.replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, max) : '';
  const count = value => Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0;
  const number = value => count(value).toLocaleString();
  const abbr = value => clean(value, 16).split(/[\s/-]+/).map(word => word[0] || '').join('').slice(0, 3).toUpperCase() || 'SRC';
  const shorten = (value, length) => value.length > length ? value.slice(0, length - 1) + '…' : value;
  const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function svg(tag, attrs, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function validRelative(value) {
    return typeof value === 'string' && value.length > 0 && value.length <= 2048 &&
      !/^[\/\\]|[\x00-\x1f\x7f\\]/.test(value) && !value.split('/').some(part => !part || part === '.' || part === '..');
  }
  function tell(message) {
    $('notice').textContent = message; $('notice').hidden = false;
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => {$('notice').hidden = true;}, 3500);
  }
  function acceptReviewedTests(value) {
    if (!isRecord(value) || typeof value.available !== 'boolean' || typeof value.running !== 'boolean') return;
    reviewedRunning=value.running; reviewedAvailable=value.available;
    const button=$('run-all-reviewed'); button.disabled=reviewedRunning || !reviewedAvailable;
    button.textContent=reviewedRunning ? 'Running reviewed tests…' : '▶ Run all reviewed tests';
    const latest=isRecord(value.latest) ? value.latest : null;
    let text=reviewedRunning ? (clean(value.progress,160) || 'Running the fixed reviewed workflows in isolated copies. Use the VS Code notification to cancel.') : reviewedAvailable ? 'Manual run: all reviewed isolated workflows. Original files are verified unchanged.' : 'Aggregate execution is not bundled. Open a reviewed workspace and use its own manual test tools.';
    if(!reviewedRunning && latest && ['PASS','FAIL','ERROR','CANCELLED','BUSY','TIMEOUT','REPORT_REJECTED','TERMINATION_UNCONFIRMED'].includes(latest.status)) {
      text=latest.status;
      if(Number.isSafeInteger(latest.testsPassed) && latest.testsPassed>=0)text+=' · '+number(latest.testsPassed)+' tests passed';
      if(Number.isSafeInteger(latest.syntaxChecksPassed) && latest.syntaxChecksPassed>=0)text+=' · '+number(latest.syntaxChecksPassed)+' syntax checks passed';
      if(Number.isSafeInteger(latest.durationMs) && latest.durationMs>=0)text+=' · '+(latest.durationMs/1000).toFixed(1)+'s';
      if(Number.isSafeInteger(latest.originalFilesVerified) && latest.originalFilesVerified>=0)text+=' · '+number(latest.originalFilesVerified)+' originals verified';
      if(Array.isArray(latest.coverage))latest.coverage.slice(0,5).forEach(item=>{if(isRecord(item)&&typeof item.project==='string'&&Number.isFinite(item.percentage)&&item.percentage>=0&&item.percentage<=100)text+=' · '+clean(item.project,100)+' coverage '+item.percentage.toFixed(2)+'%';});
      if(latest.reportText)text+=' · Fresh report opened in VS Code for case details.';
    }
    $('reviewed-run-status').textContent=text;
  }
  function send(type, project, relativePath) {
    if (!bridge) {tell('Preview only. Open this map in the Code Atlas extension to browse source.'); return;}
    if (type === 'refresh') {bridge.postMessage({type: 'refresh'}); tell('Local catalog refresh requested.'); return;}
    if (!project || !state.projects.some(item => item.id === project.id)) return;
    if (type === 'openTests' && project.testStatus === 'REVIEWED_ISOLATED_TESTS') {bridge.postMessage({type: 'openTests', id: project.id}); return;}
    if (project.status !== 'READ_ONLY_SOURCE') return;
    if (type === 'openProject') {
      const languages = project.languages.length ? project.languages : [project.primaryLanguage];
      const language = languages.includes(state.language) ? state.language : languages.includes(project.primaryLanguage) ? project.primaryLanguage : languages[0];
      bridge.postMessage({type: 'openProject', id: project.id, language});
    }
    else if (type === 'openFile' && validRelative(relativePath)) bridge.postMessage({type: 'openFile', id: project.id, relativePath});
  }
  function normalizedProjects(catalog) {
    const seen = new Set();
    return (Array.isArray(catalog.projects) ? catalog.projects : []).filter(project => {
      if (!isRecord(project) || typeof project.id !== 'string' || !/^p-[0-9a-f]{16}$/.test(project.id) || seen.has(project.id)) return false;
      seen.add(project.id); return true;
    }).map(project => ({
      ...project,
      label: clean(project.label) || 'Unnamed source root', rootPath: clean(project.rootPath, 4096),
      primaryLanguage: clean(project.primaryLanguage, 64) || 'Other',
      languages: [...new Set((Array.isArray(project.languages) ? project.languages : []).map(value => clean(value, 64)).filter(Boolean))],
      validation: isRecord(project.validation) ? project.validation : {},
      sampleFiles: (Array.isArray(project.sampleFiles) ? project.sampleFiles : []).filter(file => isRecord(file) && validRelative(file.relativePath)).slice(0, 20)
    }));
  }
  function stale(project) {return /STALE/.test(clean(project.validation.status).toUpperCase());}
  function limited(project) {return project.scanComplete === false || project.status === 'UNREADABLE';}
  function statusName(project) {
    if (project.status === 'MISSING') return 'Source missing';
    if (project.status === 'UNREADABLE') return 'Unreadable';
    if (stale(project)) return 'Syntax stale';
    if (limited(project)) return 'Limited scan';
    return 'Read only';
  }
  function badge(project) {
    const style = project.status === 'MISSING' || project.status === 'UNREADABLE' ? 'error' : stale(project) ? 'stale' : limited(project) ? 'limited' : '';
    return element('span', 'badge ' + style, statusName(project));
  }
  function filtered() {
    const query = state.search.toLocaleLowerCase();
    return state.projects.filter(project => {
      const languageMatches = !state.language || project.primaryLanguage === state.language || project.languages.includes(state.language);
      const coverageMatches = !state.coverage || (state.coverage === 'covered' && project.status === 'READ_ONLY_SOURCE' && !limited(project)) ||
        (state.coverage === 'limited' && limited(project)) || (state.coverage === 'stale' && stale(project));
      const haystack = [project.label, project.rootPath, project.primaryLanguage, ...project.languages, ...project.sampleFiles.map(file => file.relativePath)].join(' ').toLocaleLowerCase();
      return languageMatches && coverageMatches && (!query || haystack.includes(query));
    });
  }
  function acceptCatalog(catalog) {
    if (!isRecord(catalog) || catalog.schemaVersion !== 1 || !Array.isArray(catalog.projects)) return;
    state.catalog = catalog; state.projects = normalizedProjects(catalog);
    if (state.selected && !state.projects.some(project => project.id === state.selected)) {state.selected = null; state.fileDraft = '';}
    const languages = [...new Set(state.projects.flatMap(project => [project.primaryLanguage, ...project.languages]))].sort((a, b) => a.localeCompare(b));
    $('language').replaceChildren(element('option', '', 'All languages'));
    $('language').firstChild.value = '';
    languages.forEach(language => {const members = state.projects.filter(project => project.primaryLanguage === language || project.languages.includes(language)).length; const option = element('option', '', language + ' (' + number(members) + ')'); option.value = language; $('language').append(option);});
    if (!languages.includes(state.language)) state.language = '';
    $('language').value = state.language;
    const coverage = isRecord(catalog.coverage) ? catalog.coverage : {};
    $('project-total').textContent = number(state.projects.length);
    $('language-total').textContent = number(languages.length);
    $('file-total').textContent = number(coverage.codeFiles ?? state.projects.reduce((sum, project) => sum + count(project.fileCount), 0));
    $('covered-count').textContent = number(state.projects.filter(project => project.status === 'READ_ONLY_SOURCE' && project.scanComplete === true).length);
    $('limited-count').textContent = number(state.projects.filter(limited).length);
    $('excluded-count').textContent = number(coverage.excludedDirectories);
    $('stale-count').textContent = number(state.projects.filter(stale).length);
    const pending = count(catalog.validation?.pending);
    $('coverage-note').textContent = (coverage.complete === true ? 'Configured roots covered within policy. ' : 'Configured-root coverage is partial. ') +
      (coverage.scanBudgetExceeded ? 'Scan budget reached. ' : '') + (count(coverage.unreadableDirectories) ? number(coverage.unreadableDirectories) + ' unreadable directories. ' : '') +
      (pending ? number(pending) + ' syntax checks pending. ' : '') + 'Excluded counts refer to files and directories.';
    $('coverage-bases').replaceChildren();
    (Array.isArray(coverage.bases) ? coverage.bases : []).filter(isRecord).forEach(base => {
      const row = element('div', 'coverage-base');
      const limits = Array.isArray(base.limitsHit) ? base.limitsHit.map(value => clean(value, 80)).join(', ') : base.limitsHit === true ? 'yes' : String(count(base.limitsHit));
      row.append(element('code', '', clean(base.path, 4096)), element('span', '', (clean(base.status, 80) || 'UNREPORTED') + ' · ' + number(base.visitedDirectories) + ' directories visited · ' + number(base.projects) + ' source roots · limits: ' + (limits || 'none')));
      $('coverage-bases').append(row);
    });
    if (!$('coverage-bases').firstChild) $('coverage-bases').append(element('p', 'muted', 'Configured-root details have not been supplied.'));
    const stamp = clean(catalog.generatedAtUtc, 64);
    const date = new Date(stamp);
    $('updated').textContent = 'Catalog ' + (Number.isNaN(date.getTime()) ? 'timestamp unavailable' : date.toLocaleString()) + ' · refresh 60s · open-file refresh 1s';
    renderTestShortcuts(); render();
  }
  function renderTestShortcuts() {
    const targets = state.projects.filter(project => project.testStatus === 'REVIEWED_ISOLATED_TESTS').sort((a, b) => a.label.localeCompare(b.label));
    $('test-ready-count').textContent = number(targets.length); $('test-shortcuts').replaceChildren();
    for (const project of targets) {
      const button = element('button', 'test-shortcut'); button.type = 'button';
      button.append(element('strong', '', project.label + ' ↗'), element('span', '', 'Open separately reviewed workspace tooling'));
      button.addEventListener('click', () => send('openTests', project)); $('test-shortcuts').append(button);
    }
    if (!targets.length) $('test-shortcuts').append(element('p', 'muted', 'No reviewed test workspace is configured in this catalog.'));
  }
  function chooseProject(id) {
    if (state.selected !== id) state.fileDraft = '';
    state.selected = id; render();
    $('announcer').textContent = 'Selected ' + (state.projects.find(project => project.id === id)?.label || 'project');
  }
  function chooseLanguage(language) {
    state.language = state.language === language ? '' : language; $('language').value = state.language;
    state.zoom = 1; state.x = 0; state.y = 0; render();
  }
  function clickable(node, label, action) {
    node.setAttribute('tabindex', '0'); node.setAttribute('role', 'button'); node.setAttribute('aria-label', label);
    node.addEventListener('click', event => {event.stopPropagation(); action();});
    node.addEventListener('keydown', event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); event.stopPropagation(); action();}});
  }
  function serverNode(x, y) {
    const group = svg('g', {class: 'server-node', transform: `translate(${x} ${y})`});
    group.append(svg('circle', {r: 70, class: 'halo'}), svg('circle', {r: 54, class: 'core'}),
      svg('text', {'text-anchor': 'middle', y: -3, class: 'server-title'}, 'OUTLANDS'),
      svg('text', {'text-anchor': 'middle', y: 15, class: 'server-sub'}, 'AVAILABLE SOURCE'));
    $('nodes').append(group);
  }
  function edge(x1, y1, x2, y2, className = '') {
    $('edges').append(svg('path', {class: 'edge ' + className, d: `M ${x1} ${y1} Q ${(x1 + x2) / 2} ${(y1 + y2) / 2 - 16} ${x2} ${y2}`}));
  }
  function languageNode(language, projects, x, y, index, active = false) {
    const color = COLORS[index % COLORS.length];
    const group = svg('g', {class: 'node language-node' + (active ? ' active' : ''), transform: `translate(${x} ${y})`});
    group.append(svg('circle', {r: 27, class: 'outer', stroke: color}), svg('text', {'text-anchor': 'middle', y: 4, class: 'abbr'}, abbr(language)),
      svg('text', {'text-anchor': 'middle', y: 44, class: 'node-label'}, shorten(language, 22)),
      svg('text', {'text-anchor': 'middle', y: 58, class: 'node-meta'}, projects.length + ' source ' + (projects.length === 1 ? 'root' : 'roots')));
    group.append(svg('title', {}, language + ' · ' + projects.length + ' source roots. Select to focus.'));
    clickable(group, language + ', ' + projects.length + ' source roots', () => chooseLanguage(language));
    $('nodes').append(group);
  }
  function projectNode(project, x, y) {
    const selected = state.selected === project.id;
    const group = svg('g', {class: 'node project-node' + (selected ? ' selected' : ''), transform: `translate(${x} ${y})`});
    group.append(svg('circle', {r: selected ? 22 : 18, class: 'outer'}), svg('text', {'text-anchor': 'middle', y: 4, class: 'initial'}, abbr(project.label)),
      svg('text', {'text-anchor': 'middle', y: 35, class: 'node-label'}, shorten(project.label, 21)));
    group.append(svg('title', {}, project.label + '\n' + project.rootPath + '\n' + statusName(project)));
    clickable(group, project.label + ', ' + statusName(project), () => chooseProject(project.id));
    $('nodes').append(group);
  }
  function renderMap(projects) {
    $('edges').replaceChildren(); $('nodes').replaceChildren(); $('empty').hidden = projects.length > 0;
    if (state.language) {
      const shown = projects.slice(0, 24);
      serverNode(145, 370); edge(200, 370, 400, 370); languageNode(state.language, projects, 430, 370, 0, true);
      shown.forEach((project, index) => {
        const angle = -Math.PI / 2 + index / Math.max(shown.length, 1) * Math.PI * 2;
        const ring = index % 2; const radiusX = shown.length <= 12 ? 220 : ring ? 245 : 155;
        const radiusY = shown.length <= 12 ? 240 : ring ? 270 : 175;
        const x = 790 + Math.cos(angle) * radiusX, y = 370 + Math.sin(angle) * radiusY;
        edge(457, 370, x, y, 'member' + (state.selected === project.id ? ' selected' : '')); projectNode(project, x, y);
      });
      $('map-title').textContent = state.language + ' source roots'; $('map-kicker').textContent = 'LANGUAGE FOCUS';
      $('shown-count').textContent = projects.length > shown.length ? 'First 24 of ' + number(projects.length) + ' roots drawn · all matches listed below' : number(projects.length) + ' source roots shown';
    } else {
      const groups = new Map(); projects.forEach(project => {const language = project.primaryLanguage; if (!groups.has(language)) groups.set(language, []); groups.get(language).push(project);});
      const entries = [...groups].sort((a, b) => a[0].localeCompare(b[0]));
      serverNode(560, 370);
      entries.forEach(([language, members], index) => {
        const angle = -Math.PI / 2 + index / Math.max(entries.length, 1) * Math.PI * 2;
        const radiusX = entries.length > 15 && index % 2 ? 300 : 430;
        const radiusY = entries.length > 15 && index % 2 ? 190 : 278;
        const x = 560 + Math.cos(angle) * radiusX, y = 355 + Math.sin(angle) * radiusY;
        edge(560, 370, x, y); languageNode(language, members, x, y, index);
      });
      $('map-title').textContent = 'Your projects, connected.'; $('map-kicker').textContent = 'PRIMARY LANGUAGE NETWORK';
      $('shown-count').textContent = number(projects.length) + ' source roots · ' + number(entries.length) + ' primary language groups · select a language to focus';
    }
    transformMap();
  }
  function renderList(projects) {
    $('projects').replaceChildren(); $('results-count').textContent = number(projects.length);
    if (!projects.length) {$('projects').append(element('p', 'list-empty', 'No source roots match these filters.')); return;}
    projects.forEach(project => {
      const row = element('button', 'project-row' + (state.selected === project.id ? ' selected' : '')); row.type = 'button'; row.setAttribute('aria-pressed', String(state.selected === project.id));
      const mark = element('span', 'project-mark', abbr(project.primaryLanguage));
      const copy = element('span', 'project-row-copy'); copy.append(element('span', 'project-row-title', project.label), element('span', 'project-row-path', project.rootPath));
      const end = element('span', 'project-row-end'); end.append(badge(project), element('span', '', '›'));
      row.append(mark, copy, end); row.addEventListener('click', () => chooseProject(project.id)); $('projects').append(row);
    });
  }
  function fact(list, key, value) {list.append(element('dt', '', key), element('dd', '', value));}
  function renderDetail() {
    const activeInput = document.activeElement;
    const restoreFocus = activeInput?.getAttribute?.('data-file-project') === state.selected;
    const selectionStart = activeInput?.selectionStart, selectionEnd = activeInput?.selectionEnd;
    const project = state.projects.find(item => item.id === state.selected);
    const container = $('details'); container.replaceChildren();
    if (!project) {
      $('detail-title').textContent = 'Choose a project';
      container.append(element('p', 'muted', 'Select a project in the source list. Select a language node to focus the map.'), element('div', 'info-box', 'This is a live source catalog. Source availability and static syntax metadata do not establish project activity, service health, build success, or passing tests.'));
      return;
    }
    $('detail-title').textContent = project.label;
    container.append(element('p', 'detail-path', project.rootPath), badge(project));
    const chips = element('div', 'language-chips');
    [...new Set([project.primaryLanguage, ...project.languages])].forEach(language => {const chip = element('button', '', language); chip.type = 'button'; chip.addEventListener('click', () => chooseLanguage(language)); chips.append(chip);});
    container.append(chips);
    const browse = element('button', 'button primary-action', 'Browse source files ↗'); browse.type = 'button'; browse.disabled = project.status !== 'READ_ONLY_SOURCE'; browse.addEventListener('click', () => send('openProject', project)); container.append(browse);
    const facts = element('dl', 'facts'); fact(facts, 'Indexed source files', number(project.fileCount)); fact(facts, 'Coverage', project.scanComplete === true ? 'Complete within policy' : 'Limited / incomplete');
    fact(facts, 'Primary language', project.primaryLanguage); fact(facts, 'Activity', 'Not assessed'); container.append(facts);
    container.append(element('h3', 'section-label', 'Static syntax metadata'));
    const validation = project.validation;
    const status = clean(validation.status, 100).replaceAll('_', ' ') || 'NOT CHECKED';
    const syntax = element('div', 'info-box'); syntax.append(element('div', 'syntax-status', status),
      element('div', '', number(validation.syntaxPassed) + ' passed · ' + number(validation.syntaxErrors) + ' errors · ' + number(validation.pending) + ' pending · ' + number(validation.unsupported) + ' unsupported'));
    if (validation.lastCheckedAtUtc) syntax.append(element('div', 'file-hint', 'Checked: ' + clean(validation.lastCheckedAtUtc, 64)));
    container.append(syntax);
    container.append(element('h3', 'section-label', 'Testing is separate'));
    let testing = 'Static checks only. Test and runtime setup is not configured for this source root.';
    if (project.testStatus === 'REVIEWED_ISOLATED_TESTS') {
      testing = 'A reviewed workspace is configured. Isolation, copy freshness, coverage and test execution are provided by that workspace’s own tooling.';
    }
    container.append(element('div', 'info-box', testing));
    if (project.testStatus === 'REVIEWED_ISOLATED_TESTS') {
      const tests = element('button', 'button test-action', 'Open test workspace ↗'); tests.type = 'button';
      tests.addEventListener('click', () => send('openTests', project)); container.append(tests);
    }
    container.append(element('h3', 'section-label', 'Indexed source sample'));
    if (project.sampleFiles.length) {
      const files = element('div', 'file-list');
      project.sampleFiles.forEach(file => {const button = element('button', 'file-row', clean(file.relativePath, 2048)); button.type = 'button'; button.disabled = project.status !== 'READ_ONLY_SOURCE'; button.title = 'Open read-only source: ' + clean(file.language, 64); button.addEventListener('click', () => send('openFile', project, file.relativePath)); files.append(button);});
      container.append(files);
    }
    container.append(element('p', 'file-hint', 'The sample is limited to 20 files. Browse the Code Explorer for more. Only policy-approved source opens, in a read-only editor.'));
    const fileOpen = element('div', 'file-open'); const input = element('input'); input.type = 'text'; input.placeholder = 'Relative source path…'; input.maxLength = 2048; input.autocomplete = 'off'; input.spellcheck = false; input.setAttribute('aria-label', 'Relative source file path');
    input.setAttribute('data-file-project', project.id); input.value = state.fileDraft;
    input.addEventListener('input', () => {state.fileDraft = input.value.slice(0, 2048);});
    const open = element('button', '', 'Open'); open.type = 'button'; open.disabled = project.status !== 'READ_ONLY_SOURCE';
    const openRelative = () => {const relativePath = input.value.trim(); if (!validRelative(relativePath)) {tell('Enter a relative file path without traversal or empty segments.'); return;} send('openFile', project, relativePath);};
    open.addEventListener('click', openRelative); input.addEventListener('keydown', event => {if (event.key === 'Enter') {event.preventDefault(); openRelative();}});
    fileOpen.append(input, open); container.append(fileOpen);
    if (restoreFocus) {input.focus(); if (Number.isInteger(selectionStart) && Number.isInteger(selectionEnd)) input.setSelectionRange(selectionStart, selectionEnd);}
  }
  function render() {const projects = filtered(); renderMap(projects); renderList(projects); renderDetail();}
  function transformMap() {$('scene').setAttribute('transform', `translate(${state.x} ${state.y}) translate(560 370) scale(${state.zoom}) translate(-560 -370)`); $('zoom-label').textContent = Math.round(state.zoom * 100) + '%';}
  function zoom(delta) {state.zoom = Math.max(.55, Math.min(2.4, state.zoom + delta)); transformMap();}
  $('search').addEventListener('input', event => {state.search = event.target.value.slice(0, 512); render();});
  $('language').addEventListener('change', event => {state.language = event.target.value; state.zoom = 1; state.x = 0; state.y = 0; render();});
  $('coverage-filter').addEventListener('change', event => {state.coverage = event.target.value; render();});
  $('clear').addEventListener('click', () => {state.search = ''; state.language = ''; state.coverage = ''; $('search').value = ''; $('language').value = ''; $('coverage-filter').value = ''; render();});
  $('refresh').addEventListener('click', () => send('refresh'));
  $('run-all-reviewed').addEventListener('click', () => {if(bridge && reviewedAvailable && !reviewedRunning){reviewedRunning=true;$('run-all-reviewed').disabled=true;bridge.postMessage({type:'runAllReviewedTests'});}});
  $('zoom-in').addEventListener('click', () => zoom(.15)); $('zoom-out').addEventListener('click', () => zoom(-.15));
  $('reset').addEventListener('click', () => {state.zoom = 1; state.x = 0; state.y = 0; transformMap();});
  $('viewport').addEventListener('wheel', event => {if (event.ctrlKey || event.metaKey) {event.preventDefault(); zoom(event.deltaY < 0 ? .1 : -.1);}}, {passive: false});
  $('viewport').addEventListener('pointerdown', event => {if (event.button !== 0 || event.target.closest('.node')) return; pointer = {id: event.pointerId, x: event.clientX, y: event.clientY}; $('viewport').setPointerCapture(event.pointerId); $('viewport').classList.add('dragging');});
  $('viewport').addEventListener('pointermove', event => {if (!pointer || pointer.id !== event.pointerId) return; const bounds = $('viewport').getBoundingClientRect(); state.x += (event.clientX - pointer.x) * 1120 / Math.max(bounds.width, 1); state.y += (event.clientY - pointer.y) * 740 / Math.max(bounds.height, 1); pointer.x = event.clientX; pointer.y = event.clientY; transformMap();});
  const endPointer = () => {pointer = undefined; $('viewport').classList.remove('dragging');};
  $('viewport').addEventListener('pointerup', endPointer); $('viewport').addEventListener('pointercancel', endPointer); $('viewport').addEventListener('lostpointercapture', endPointer);
  $('viewport').addEventListener('keydown', event => {
    if (event.target !== $('viewport')) return;
    const shifts = {ArrowLeft: [25, 0], ArrowRight: [-25, 0], ArrowUp: [0, 25], ArrowDown: [0, -25]};
    if (shifts[event.key]) {event.preventDefault(); state.x += shifts[event.key][0]; state.y += shifts[event.key][1]; transformMap();}
    else if (event.key === '+' || event.key === '=') {event.preventDefault(); zoom(.15);}
    else if (event.key === '-') {event.preventDefault(); zoom(-.15);}
    else if (event.key === '0') {event.preventDefault(); state.zoom = 1; state.x = 0; state.y = 0; transformMap();}
  });
  window.addEventListener('message', event => {if(!isRecord(event.data))return;if(event.data.type==='catalog')acceptCatalog(event.data.catalog);if(event.data.type==='reviewedTests')acceptReviewedTests(event.data.state);});
  acceptCatalog(window.INITIAL_CATALOG);
  acceptReviewedTests(window.INITIAL_REVIEWED_TESTS || {available:false,running:false,latest:null});
})();
