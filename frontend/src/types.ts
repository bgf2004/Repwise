export type Exercise = 'squat' | 'curl';
export type RepDetail = {index:number; down_seconds:number; up_seconds:number; total_seconds:number; range_degrees:number};
export type SetRecord = {
 id:string; workout_id?:string; exercise:Exercise; weight:number; unit:'lb'|'kg'; target_reps:number; reps:number;
 set_number:number; started_at:string; ended_at:string; rest_before_seconds:number|null; tempo:'natural'|'controlled';
 effort_rir:number|null; source:'camera'|'manual'; rep_details:RepDetail[]; notes:string; tracked_reps?:number; reps_corrected?:boolean;
};
export type Workout = {id:string; started_at:string; ended_at:string|null; sets:SetRecord[]};
export type Recommendation = {recommended_seconds:number; range_low:number; range_high:number; status:'baseline'|'learning'|'personalized'; sample_count:number; session_count:number; explanation:string; buckets:{rest_seconds:number;samples:number;success_rate:number;median_reps:number}[]; excluded_count:number};
export const exerciseNames:Record<Exercise,string> = {squat:'Squat',curl:'Biceps curl'};
