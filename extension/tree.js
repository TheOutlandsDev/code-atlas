'use strict';
class SourceTree {
  constructor(vscode, provider, getProjects) {
    this.vscode = vscode; this.provider = provider; this.getProjects = getProjects;
    this.events = new vscode.EventEmitter(); this.onDidChangeTreeData = this.events.event;
    this.nodes = new Map();
  }
  node(key, data) { if (!this.nodes.has(key)) this.nodes.set(key,Object.freeze({...data,key})); return this.nodes.get(key); }
  refresh() { this.nodes.clear(); this.events.fire(); }
  languages() { return [...new Set([...this.getProjects().values()].flatMap(p => p.languages.length ? p.languages : [p.primaryLanguage || 'Unclassified']))].sort(); }
  projectNode(id, language) { return this.node('p:'+language+':'+id,{kind:'project',id,language,rel:''}); }
  hasReviewedTests(project) { return !!project && project.testStatus === 'REVIEWED_ISOLATED_TESTS' && this.provider.policy.reviewedTests.has(project.rootPath); }
  reviewedProjectId(element) {
    if (!element || this.nodes.get(element.key) !== element || element.kind !== 'project' || !this.hasReviewedTests(this.getProjects().get(element.id))) throw new Error('Reviewed project node required');
    return element.id;
  }
  getChildren(element) {
    if (!element) return this.languages().map(language => this.node('l:'+language,{kind:'language',language}));
    if (this.nodes.get(element.key) !== element) return [];
    if (element.kind === 'language') return [...this.getProjects().values()].filter(p => (p.languages.length ? p.languages : [p.primaryLanguage || 'Unclassified']).includes(element.language)).sort((a,b) => a.label.localeCompare(b.label)).map(p => this.projectNode(p.id,element.language));
    if (element.kind === 'project' || element.kind === 'directory') {
      const project = this.getProjects().get(element.id); if (!project || project.status !== 'READ_ONLY_SOURCE') return [];
      try {
        return this.provider.readDirectory(this.provider.uri(element.id,element.rel)).map(([name,type]) => {
          const rel = element.rel ? element.rel + '/' + name : name;
          return this.node('f:'+element.language+':'+element.id+':'+rel,{kind:type === this.vscode.FileType.Directory ? 'directory' : 'file',id:element.id,language:element.language,rel,name,parent:element});
        });
      } catch { return [this.node('e:'+element.key,{kind:'notice',label:'Unavailable or directory limit reached'})]; }
    }
    return [];
  }
  getParent(element) {
    if (this.nodes.get(element.key) !== element) return undefined;
    if (element.parent) return element.parent;
    if (element.kind === 'project') return this.node('l:'+element.language,{kind:'language',language:element.language});
    return undefined;
  }
  getTreeItem(element) {
    const v = this.vscode;
    if (!element || this.nodes.get(element.key) !== element) return new v.TreeItem('Unavailable',v.TreeItemCollapsibleState.None);
    const project = this.getProjects().get(element.id);
    const label = element.kind === 'language' ? element.language : element.kind === 'project' ? (project ? project.label : 'Unavailable') : (element.name || element.label);
    const expandable = ['language','project','directory'].includes(element.kind);
    const item = new v.TreeItem(label,expandable ? v.TreeItemCollapsibleState.Collapsed : v.TreeItemCollapsibleState.None);
    item.id = element.key; item.contextValue = element.kind;
    if (element.kind === 'language') { const count = [...this.getProjects().values()].filter(p => (p.languages.length ? p.languages : [p.primaryLanguage || 'Unclassified']).includes(element.language)).length; item.description = count+' source '+(count === 1 ? 'root' : 'roots'); }
    if (element.kind === 'project' && project) {
      const reviewed = this.hasReviewedTests(project);
      item.contextValue = reviewed ? 'projectReviewedTests' : 'project';
      item.description = (project.status === 'READ_ONLY_SOURCE' ? project.fileCount+' code files · read only' : project.status)+(reviewed ? ' · reviewed workspace available' : '');
      item.tooltip = project.rootPath+'\n'+project.status+(reviewed ? '\nRight-click to open the reviewed test workspace.' : '');
    }
    if (element.kind === 'file') { item.resourceUri = this.provider.uri(element.id,element.rel); item.command = {command:'codeAtlas.openFile',title:'Open read-only source',arguments:[element.id,element.rel]}; }
    item.iconPath = new v.ThemeIcon(element.kind === 'language' ? 'symbol-namespace' : element.kind === 'project' ? 'repo' : element.kind === 'directory' ? 'folder' : element.kind === 'notice' ? 'warning' : 'file-code');
    return item;
  }
  dispose() { this.events.dispose(); this.nodes.clear(); }
}
module.exports = {SourceTree};
