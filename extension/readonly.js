'use strict';
const fs = require('fs');
const {relative} = require('./policy');
const SCHEME = 'code-atlas';
class ReadonlyProvider {
  constructor(vscode, policy, getProjects, isAllowed = () => true) {
    this.vscode = vscode; this.policy = policy; this.getProjects = getProjects;
    this.events = new vscode.EventEmitter(); this.onDidChangeFile = this.events.event;
    this.open = new Map(); this.disposed = false; this.isAllowed = isAllowed; this.timer = null;
  }
  uri(id, rel = '') { relative(rel, true); return this.vscode.Uri.from({scheme:SCHEME, path:'/' + id + (rel ? '/' + rel : '')}); }
  parse(uri, allowUnavailable = false) {
    if (!this.isAllowed() || this.disposed || !uri || uri.scheme !== SCHEME || uri.authority || uri.query || uri.fragment || typeof uri.path !== 'string') throw new Error('Invalid source URI');
    const match = /^\/(p-[0-9a-f]{16})(?:\/(.*))?$/.exec(uri.path);
    if (!match) throw new Error('Invalid source URI');
    const rel = relative(match[2] || '', true); const project = this.getProjects().get(match[1]);
    if (!project || (!allowUnavailable && project.status !== 'READ_ONLY_SOURCE')) throw new Error('Source root is unavailable');
    return {id:match[1], rel, project};
  }
  denied(error) { return this.vscode.FileSystemError.NoPermissions(error && error.message ? error.message : 'Read-only source policy denied access'); }
  stat(uri) {
    try {
      const {project,rel} = this.parse(uri); const {stat} = this.policy.resolve(project.rootPath, rel);
      return {type:stat.isDirectory() ? this.vscode.FileType.Directory : this.vscode.FileType.File, ctime:stat.ctimeMs,mtime:stat.mtimeMs,size:stat.size,permissions:this.vscode.FilePermission.Readonly};
    } catch (e) { throw this.denied(e); }
  }
  readDirectory(uri) {
    try { const {project,rel} = this.parse(uri); return this.policy.list(project.rootPath,rel).map(e => [e.name,e.directory ? this.vscode.FileType.Directory : this.vscode.FileType.File]); }
    catch (e) { throw this.denied(e); }
  }
  readFile(uri) {
    try { const {project,rel} = this.parse(uri); return this.policy.read(project.rootPath,rel); }
    catch (e) { throw this.denied(e); }
  }
  watch() { return {dispose(){}}; } // Open-document polling below never follows replacement symlinks.
  writeFile() { throw this.denied(); }
  delete() { throw this.denied(); }
  rename() { throw this.denied(); }
  createDirectory() { throw this.denied(); }
  copy() { throw this.denied(); }
  watchOpen(uri) {
    if (this.disposed || !uri || uri.scheme !== SCHEME) return false;
    const key = uri.toString(); if (this.open.has(key)) return true;
    if (this.open.size >= 128) return false;
    let source;
    try {
      source = this.parse(uri,true); relative(source.rel);
      this.policy.authorizeRoot(source.project.rootPath,false);
      if (this.policy.excluded(source.project.rootPath+'/'+source.rel,source.project.rootPath) || !this.policy.language(source.rel)) return false;
    }
    catch { return false; }
    let stamp = null;
    try { stamp = this.stamp(this.policy.resolve(source.project.rootPath,source.rel,false).stat); } catch {}
    this.open.set(key,{uri,stamp});
    if (!this.timer) { this.timer = setInterval(() => this.poll(),1000); this.timer.unref?.(); }
    return true;
  }
  stamp(stat) { return [stat.dev,stat.ino,stat.size,stat.mtimeMs,stat.ctimeMs].join(':'); }
  unwatch(uri) { this.open.delete(uri.toString()); if (!this.open.size && this.timer) { clearInterval(this.timer); this.timer = null; } }
  poll() {
    if (this.disposed) return;
    for (const item of this.open.values()) {
      let stamp = null;
      try { const s = this.parse(item.uri); stamp = this.stamp(this.policy.resolve(s.project.rootPath,s.rel,false).stat); } catch {}
      if (stamp !== item.stamp) {
        const type = stamp === null ? this.vscode.FileChangeType.Deleted : item.stamp === null ? this.vscode.FileChangeType.Created : this.vscode.FileChangeType.Changed;
        item.stamp = stamp; this.events.fire([{type,uri:item.uri}]);
      }
    }
  }
  reconcile() { this.poll(); }
  dispose() { this.disposed = true; if (this.timer) clearInterval(this.timer); this.timer = null; this.open.clear(); this.events.dispose(); }
}
module.exports = {ReadonlyProvider, SCHEME};
