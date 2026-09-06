import { appendFile } from 'node:fs/promises';
const marker = (phase: string) => appendFile('/tmp/gjc-keychron-live-experiments/ui-fixture-markers.jsonl',JSON.stringify({phase,at:Date.now()})+'\n');
export default function(api: any) {
  api.registerCommand('lab-confirm',{description:'Local observation test confirmation',handler:async (_:string,ctx:any)=>{
    await marker('confirm-open');
    const result=await ctx.ui.confirm('KEYCHRON FIXTURE APPROVAL','Approve the local fixture only?');
    await marker(result?'confirm-accepted':'confirm-declined');
    ctx.ui.notify('FIXTURE_CONFIRM_DONE','info');
  }});
  api.registerCommand('lab-input',{description:'Local observation test input',handler:async (_:string,ctx:any)=>{
    await marker('input-open');
    const result=await ctx.ui.input('KEYCHRON FIXTURE INPUT','fixture');
    await marker(result===undefined?'input-cancelled':'input-returned');
    ctx.ui.notify('FIXTURE_INPUT_DONE','info');
  }});
}
