'use strict';
const fs = require('fs');
const {ROOT, canonical, projectId, relative} = require('./policy');
const CATALOG_FILE = ROOT + '/state/catalog.json';
const text = (value, limit = 512) => typeof value === 'string' && value.length <= limit && !/[\x00-\x1f\x7f]/.test(value);
const number = value => Number.isSafeInteger(value) && value >= 0;
function emptyCatalog() { return {schemaVersion:1,generation:0,generatedAtUtc:null,projects:[],coverage:{bases:[],projectCount:0,codeFiles:0,complete:false,limited:true,unreadableDirectories:0,excludedDirectories:0,scanBudgetExceeded:false,durationMs:0},validation:{mode:'static_only',supportedLanguages:[],checkedThisScan:0,cacheEntries:0,errors:0,pending:0}}; }
function validateCatalog(raw, policy) {
  if (!raw || raw.schemaVersion !== 1 || !Array.isArray(raw.projects) || raw.projects.length > (policy.raw.maxProjects || 1500) || !raw.coverage || !raw.validation || raw.validation.mode !== 'static_only') throw new Error('Invalid catalog schema');
  if (!(number(raw.generation) || text(raw.generation,128)) || !text(raw.generatedAtUtc,64)) throw new Error('Invalid catalog generation');
  const ids = new Set(), roots = new Set();
  const projects = raw.projects.map(p => {
    if (!p || !text(p.rootPath,4096) || !text(p.label,256) || !p.label || p.id !== projectId(p.rootPath) || ids.has(p.id) || roots.has(p.rootPath)) throw new Error('Invalid catalog project');
    policy.authorizeRoot(p.rootPath,false); ids.add(p.id); roots.add(p.rootPath);
    if (!['READ_ONLY_SOURCE','MISSING','UNREADABLE'].includes(p.status) || typeof p.scanComplete !== 'boolean' || !number(p.fileCount) || !Array.isArray(p.languages) || p.languages.length > 100 || !p.languages.every(x => text(x,80)) || !text(p.primaryLanguage,80)) throw new Error('Invalid catalog project metadata');
    if (!Array.isArray(p.sampleFiles) || p.sampleFiles.length > 100) throw new Error('Invalid catalog samples');
    const samples = p.sampleFiles.map(s => {
      relative(s.relativePath); if (s.relativePath.length > 4096 || policy.excluded(p.rootPath+'/'+s.relativePath,p.rootPath) || !policy.language(s.relativePath) || !text(s.language,80)) throw new Error('Invalid catalog source sample');
      return {relativePath:s.relativePath,language:s.language};
    });
    if (!['REVIEWED_ISOLATED_TESTS','NOT_CONFIGURED'].includes(p.testStatus) || !['BASELINE_CURRENT','SOURCE_CHANGED','NOT_CONFIGURED'].includes(p.isolatedCopyState)) throw new Error('Invalid catalog test metadata');
    if (p.testStatus === 'REVIEWED_ISOLATED_TESTS' && !policy.reviewedTests.has(p.rootPath)) throw new Error('Unknown reviewed test root');
    const v = p.validation;
    if (!v || !text(v.status,80) || !['syntaxPassed','syntaxErrors','pending','unsupported'].every(k => number(v[k])) || !(v.lastCheckedAtUtc === null || text(v.lastCheckedAtUtc,64))) throw new Error('Invalid project validation');
    return {id:p.id,label:p.label,rootPath:p.rootPath,languages:[...new Set(p.languages)],primaryLanguage:p.primaryLanguage,fileCount:p.fileCount,sourceFingerprint:text(p.sourceFingerprint,128) ? p.sourceFingerprint : '',status:p.status,scanComplete:p.scanComplete,sampleFiles:samples,validation:{status:v.status,syntaxPassed:v.syntaxPassed,syntaxErrors:v.syntaxErrors,pending:v.pending,unsupported:v.unsupported,lastCheckedAtUtc:v.lastCheckedAtUtc},testStatus:p.testStatus,isolatedCopyState:p.isolatedCopyState};
  });
  const c = raw.coverage;
  if (!Array.isArray(c.bases) || c.bases.length > 100 || !['projectCount','codeFiles','unreadableDirectories','excludedDirectories','durationMs'].every(k => number(c[k])) || c.projectCount !== projects.length || !['complete','limited','scanBudgetExceeded'].every(k => typeof c[k] === 'boolean')) throw new Error('Invalid catalog coverage');
  const bases = c.bases.map(b => { if (!b || !policy.bases.includes(b.path) || !text(b.status,80) || !number(b.visitedDirectories) || !number(b.projects) || !(number(b.limitsHit) || typeof b.limitsHit === 'boolean')) throw new Error('Invalid base coverage'); return {path:b.path,status:b.status,visitedDirectories:b.visitedDirectories,projects:b.projects,limitsHit:b.limitsHit}; });
  const v = raw.validation;
  if (!Array.isArray(v.supportedLanguages) || !v.supportedLanguages.every(x => text(x,80)) || !['checkedThisScan','cacheEntries','errors','pending'].every(k => number(v[k]))) throw new Error('Invalid catalog validation');
  return {schemaVersion:1,generation:raw.generation,generatedAtUtc:raw.generatedAtUtc,projects,coverage:{bases,projectCount:c.projectCount,codeFiles:c.codeFiles,complete:c.complete,limited:c.limited,unreadableDirectories:c.unreadableDirectories,excludedDirectories:c.excludedDirectories,scanBudgetExceeded:c.scanBudgetExceeded,durationMs:c.durationMs},validation:{mode:'static_only',supportedLanguages:v.supportedLanguages,checkedThisScan:v.checkedThisScan,cacheEntries:v.cacheEntries,errors:v.errors,pending:v.pending}};
}
function readCatalog(policy) {
  canonical(CATALOG_FILE,false); const stat = fs.statSync(CATALOG_FILE); if (stat.size > 16777216) throw new Error('Catalog is too large');
  return validateCatalog(JSON.parse(fs.readFileSync(CATALOG_FILE,'utf8')),policy);
}
module.exports = {readCatalog,validateCatalog,emptyCatalog,CATALOG_FILE};
