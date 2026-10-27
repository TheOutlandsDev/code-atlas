'use strict';
// Test-only development helper. The installed Code Atlas VSIX remains unchanged.
// Use a normal development window: --extensionTestsPath intentionally uses
// in-memory IDE storage and cannot qualify real restart persistence or trust.
exports.activate = () => {
  setTimeout(async () => {
    try { await require('./native-check.cjs').run(); }
    catch { /* The bounded JSON report is the driver's authoritative result. */ }
    finally { await require('vscode').commands.executeCommand('workbench.action.quit'); }
  }, 500);
  return {};
};
exports.deactivate = () => {};
