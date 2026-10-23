'use strict';
// Workspace navigation is portable. Deployment-specific aggregate executors are deliberately not bundled.
class ReviewedTests {
  constructor(vscode,onChange,status){this.onChange=onChange;this.status=status;}
  state(){return {available:false,running:false,latest:null};}
  async run(){this.status('AGGREGATE_NOT_CONFIGURED');return {status:'NOT_CONFIGURED'};}
  dispose(){}
}
module.exports={ReviewedTests};
