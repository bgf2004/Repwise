export async function api<T>(path:string, method='GET', body?:unknown):Promise<T> {
 const response=await fetch('/api'+path,{method,headers:body ? {'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const message=typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map((e:{msg:string})=>e.msg).join('. '):'Unable to save. Please try again.';throw new Error(message);}
 return data;
}
