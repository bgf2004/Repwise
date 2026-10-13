import {describe,it,expect} from 'vitest';
import {tempoFeedback} from './feedback';
const rep=(up:number)=>({index:1,down_seconds:1,up_seconds:up,total_seconds:up+1,range_degrees:90});
describe('observable tempo summaries',()=>{
 it('does not invent a trend with too few reps',()=>expect(tempoFeedback([rep(1)],false)).toContain('at least four'));
 it('compares disjoint first and last reps',()=>expect(tempoFeedback([rep(1),rep(1),rep(2),rep(2)],false)).toContain('100% longer'));
 it('explains controlled tempo without equating it to fatigue',()=>expect(tempoFeedback([rep(1),rep(1),rep(2),rep(2)],true)).toContain('Deliberately slow'));
 it('ignores invalid measurements',()=>expect(tempoFeedback([rep(0),rep(NaN),rep(1),rep(1)],false)).toContain('at least four'));
});
