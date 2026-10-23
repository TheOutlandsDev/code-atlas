'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const ROOT = process.env.CODE_ATLAS_HOME || path.join(os.homedir(), '.code-atlas');
if (!path.isAbsolute(ROOT) || path.normalize(ROOT) !== ROOT || /[\x00-\x1f\x7f\\]/.test(ROOT)) throw new Error('CODE_ATLAS_HOME must be a canonical absolute path');
const POLICY_FILE = ROOT + '/policy.json';
const MAX_BYTES = 2097152;
const inside = (base, file) => file === base || file.startsWith(base + '/');
const absolute = value => typeof value === 'string' && value.startsWith('/') && path.normalize(value) === value && !/[\x00-\x1f\x7f\\]/.test(value);
const projectId = root => 'p-' + crypto.createHash('sha256').update(root).digest('hex').slice(0, 16);
function relative(value, allowEmpty = false) {
  if (typeof value !== 'string' || (!allowEmpty && !value) || /[\x00-\x1f\x7f\\]/.test(value) || value.startsWith('/')) throw new Error('Invalid relative source path');
  if (value && value.split('/').some(p => !p || p === '.' || p === '..')) throw new Error('Invalid relative source path');
  return value;
}
function canonical(file, directory) {
  if (!absolute(file)) throw new Error('Invalid absolute source path');
  let current = '/';
  for (const segment of file.split('/').filter(Boolean)) {
    current = path.join(current, segment);
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink()) throw new Error('Symbolic links are excluded');
    if (current !== file && !stat.isDirectory()) throw new Error('Invalid ancestor');
  }
  if (fs.realpathSync(file) !== file) throw new Error('Noncanonical source path');
  const stat = fs.lstatSync(file);
  if (directory === true && !stat.isDirectory()) throw new Error('Not a source directory');
  if (directory === false && !stat.isFile()) throw new Error('Not a regular source file');
  fs.accessSync(file, fs.constants.R_OK);
  return stat;
}
class Policy {
  constructor(raw) {
    if (!raw || raw.schemaVersion !== 1 || !Array.isArray(raw.bases) || !Array.isArray(raw.seedRoots) || !raw.codeExtensions || !raw.manifestNames) throw new Error('Invalid source policy');
    this.raw = JSON.parse(JSON.stringify(raw));
    this.bases = raw.bases.map(p => { if (!absolute(p) || p === '/') throw new Error('Invalid policy base'); return p; });
    this.seeds = new Set(raw.seedRoots.map(p => { if (!absolute(p) || p === '/') throw new Error('Invalid seed root'); return p; }));
    this.names = new Set((raw.excludedDirectoryNames || []).map(p => p.toLowerCase()));
    this.patterns = (raw.excludedDirectoryPatterns || []).map(p => new RegExp(p, 'i'));
    this.prefixes = (raw.excludedPathPrefixes || []).map(p => { if (!absolute(p)) throw new Error('Invalid excluded prefix'); return p; });
    this.maxBytes = Math.min(Number(raw.maxFileBytes) || MAX_BYTES, MAX_BYTES);
    this.maxEntries = Math.min(Number(raw.maxDirectoryEntries) || 5000, 10000);
    this.extensions = Object.freeze(Object.assign(Object.create(null),raw.codeExtensions));
    this.manifests = Object.freeze(Object.assign(Object.create(null),raw.manifestNames));
    this.reviewedTests = new Map();
    for (const entry of raw.reviewedTests || []) {
      if (!entry || !absolute(entry.rootPath) || !this.base(entry.rootPath) || !absolute(entry.workspace) || !entry.workspace.endsWith('.code-workspace') || this.reviewedTests.has(entry.rootPath)) throw new Error('Invalid reviewed workspace target');
      this.reviewedTests.set(entry.rootPath, Object.freeze({workspace:entry.workspace}));
    }
  }
  base(root) { return this.bases.filter(base => inside(base, root)).sort((a,b) => b.length-a.length)[0] || (this.seeds.has(root) ? root : null); }
  excluded(file, root) {
    if (this.prefixes.some(prefix => inside(prefix, file))) return true;
    const base = this.base(root);
    if (!base || !inside(root, file)) return true;
    // Apply policy below the authorized base, including the project name. Ancestors are never matched by name.
    const parts = path.relative(this.seeds.has(root) ? root : base, file).split('/').filter(Boolean);
    return parts.some(part => part.startsWith('.') || this.names.has(part.toLowerCase()) || this.patterns.some(re => re.test(part)));
  }
  authorizeRoot(root, checkDisk = true) {
    if (!absolute(root) || !this.base(root) || this.excluded(root, root)) throw new Error('Source root is outside policy');
    if (checkDisk) canonical(root, true);
    return root;
  }
  language(file) { return this.manifests[path.basename(file)] || this.extensions[path.extname(file)] || null; }
  resolve(root, rel = '', directory) {
    this.authorizeRoot(root, false); relative(rel, true);
    const file = rel ? root + '/' + rel : root;
    if (this.excluded(file, root)) throw new Error('Excluded source path');
    if (directory === false && !this.language(file)) throw new Error('Unsupported source file');
    const stat = canonical(file, directory);
    if (stat.isFile() && (!this.language(file) || stat.size > this.maxBytes)) throw new Error('Unsupported or oversized source file');
    return {file, stat};
  }
  read(root, rel) {
    const before = this.resolve(root, relative(rel), false);
    let fd;
    try {
      fd = fs.openSync(before.file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
      const stat = fs.fstatSync(fd);
      // Resolve only our own descriptor. This closes an ancestor-rename/symlink race before reading bytes.
      if (!stat.isFile() || stat.size > this.maxBytes || stat.dev !== before.stat.dev || stat.ino !== before.stat.ino || fs.realpathSync('/proc/self/fd/' + fd) !== before.file) throw new Error('Source changed while opening');
      const again = this.resolve(root, rel, false);
      if (again.stat.dev !== stat.dev || again.stat.ino !== stat.ino) throw new Error('Source identity changed');
      const buffer = Buffer.alloc(Math.min(stat.size + 1, this.maxBytes + 1));
      let total = 0;
      while (total < buffer.length) { const count = fs.readSync(fd, buffer, total, buffer.length - total, null); if (!count) break; total += count; }
      const after = fs.fstatSync(fd);
      if (total > this.maxBytes || after.size > this.maxBytes || after.size !== stat.size || after.mtimeMs !== stat.mtimeMs || after.ctimeMs !== stat.ctimeMs) throw new Error('Source changed while reading');
      return buffer.subarray(0, total);
    } finally { if (fd !== undefined) fs.closeSync(fd); }
  }
  list(root, rel = '') {
    const {file,stat} = this.resolve(root, rel, true);
    const fd = fs.openSync(file,fs.constants.O_RDONLY | fs.constants.O_DIRECTORY | fs.constants.O_NOFOLLOW);
    let dir; const result = []; let count = 0;
    try {
      const opened = fs.fstatSync(fd);
      if (!opened.isDirectory() || opened.dev !== stat.dev || opened.ino !== stat.ino || fs.realpathSync('/proc/self/fd/'+fd) !== file) throw new Error('Source directory changed while opening');
      const again = this.resolve(root,rel,true);
      if (again.stat.dev !== opened.dev || again.stat.ino !== opened.ino) throw new Error('Source directory identity changed');
      dir = fs.opendirSync('/proc/self/fd/'+fd);
      let item;
      while ((item = dir.readSync())) {
        if (++count > this.maxEntries) throw new Error('Directory entry limit reached; narrow the source directory');
        const childRel = rel ? rel + '/' + item.name : item.name;
        if (item.isSymbolicLink() || this.excluded(root + '/' + childRel, root)) continue;
        try {
          const found = this.resolve(root, childRel, item.isDirectory() ? true : false);
          if (found.stat.isDirectory() || found.stat.isFile()) result.push({name:item.name, directory:found.stat.isDirectory()});
        } catch { /* Unreadable, unsupported, special, and raced paths stay hidden. */ }
      }
    } finally { if (dir) dir.closeSync(); fs.closeSync(fd); }
    return result.sort((a,b) => Number(b.directory)-Number(a.directory) || a.name.localeCompare(b.name));
  }
}
function loadPolicy() {
  if (!fs.existsSync(POLICY_FILE)) return new Policy({...JSON.parse(fs.readFileSync(path.join(__dirname,'../examples/policy.example.json'),'utf8')),bases:[],seedRoots:[]});
  canonical(POLICY_FILE, false);
  const stat = fs.statSync(POLICY_FILE); if (stat.size > 1048576) throw new Error('Policy is too large');
  return new Policy(JSON.parse(fs.readFileSync(POLICY_FILE, 'utf8')));
}
module.exports = {Policy, loadPolicy, projectId, relative, canonical, inside, ROOT, POLICY_FILE};
