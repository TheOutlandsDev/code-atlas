'use strict';
const childProcess=require('child_process');
const path=require('path');
const {ROOT}=require('./policy');
class Scanner {
  constructor(onComplete,onStatus,extensionPath,runtime={}){this.spawn=runtime.spawn||childProcess.spawn;this.kill=runtime.kill||process.kill.bind(process);this.extensionPath=extensionPath;this.onComplete=onComplete;this.onStatus=onStatus;this.child=null;this.pending=null;this.disposed=false;this.blocked=false;}
  request(){
    if(this.disposed||this.blocked)return Promise.resolve({status:this.blocked?'TERMINATION_UNCONFIRMED':'CANCELLED'});
    if(this.pending)return this.pending;
    this.pending=this.once().finally(()=>{this.pending=null;});return this.pending;
  }
  stop(child){if(child&&Number.isInteger(child.pid)&&child.pid>1){try{this.kill(-child.pid,'SIGTERM');}catch{}const timer=setTimeout(()=>{if(this.child===child){try{this.kill(-child.pid,'SIGKILL');}catch{}}},1000);timer.unref?.();}}
  once(){return new Promise(resolve=>{
    if(this.disposed)return resolve({status:'CANCELLED'});
    let child,done=false,timedOut=false,deadline,finalDeadline;
    const finish=async(code,confirmed=true)=>{
      if(done)return;done=true;clearTimeout(deadline);clearTimeout(finalDeadline);
      if(confirmed&&this.child===child)this.child=null;if(!confirmed)this.blocked=true;
      let result={status:!confirmed?'TERMINATION_UNCONFIRMED':this.disposed?'CANCELLED':timedOut?'TIMEOUT':code===0?'PASS':'ERROR'};
      if(result.status==='PASS'){try{await this.onComplete();}catch{result={status:'CATALOG_REJECTED'};}}
      this.onStatus(result.status);resolve(result);
    };
    try{
      this.onStatus('SCANNING');
      child=this.spawn('/usr/bin/python3',['-I','-B',path.join(this.extensionPath,'tools/scan.py')],{cwd:ROOT,shell:false,detached:true,stdio:['ignore','ignore','ignore'],env:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8',CODE_ATLAS_HOME:ROOT,PYTHONDONTWRITEBYTECODE:'1'}});
      this.child=child;child.once('error',()=>{void finish(null);});child.once('close',code=>{void finish(code);});
      deadline=setTimeout(()=>{timedOut=true;this.stop(child);finalDeadline=setTimeout(()=>{void finish(null,false);},2000);finalDeadline.unref?.();},25000);deadline.unref?.();
    }catch{void finish(null);}
  });}
  dispose(){this.disposed=true;if(this.child)this.stop(this.child);}
}
module.exports={Scanner};
