import type {RepDetail} from './types';
export function tempoFeedback(reps:RepDetail[],controlled:boolean):string {
 const valid=reps.filter(r=>Number.isFinite(r.up_seconds)&&r.up_seconds>0&&Number.isFinite(r.range_degrees));
 if(valid.length<4)return 'Complete at least four tracked reps to compare the beginning and end of a set.';
 const n=Math.min(3,Math.floor(valid.length/2));
 const mean=(xs:number[])=>xs.reduce((a,b)=>a+b,0)/xs.length;
 const start=mean(valid.slice(0,n).map(r=>r.up_seconds));
 const end=mean(valid.slice(-n).map(r=>r.up_seconds));
 const change=Math.round((end/start-1)*100);
 const observation=Math.abs(change)<10?'Your rising time stayed consistent through this set.':`Your last ${n} reps took about ${Math.abs(change)}% ${change>0?'longer':'less time'} to rise than your first ${n}.`;
 return observation+(controlled?' Deliberately slow tempo is recorded as a separate comparison.':' This describes timing, not a form or fatigue diagnosis.');
}
