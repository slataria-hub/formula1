// Browser-only user state. Never mutate the official dataset or read the legacy data.json.
export const STORAGE_KEY='f1-analytics:v2:user:1';
const stableKey=b=>JSON.stringify([b.externalEventId,b.season,b.kind]);
const safeId=id=>typeof id==='string'&&id.length>0&&!['__proto__','constructor','prototype'].includes(id);
const idPattern=/^[a-z][a-z0-9_-]*:[A-Za-z0-9_.-]+$/;
export function emptyStore(year){return {version:1,user:{schemaVersion:'2.0.0',predictions:[],overrides:[],preferences:{selectedSeason:year,theme:'auto'}},bindings:{}};}
export function assertStore(z){
 if(!z||z.version!==1||z.user?.schemaVersion!=='2.0.0'||!Array.isArray(z.user.predictions)||!Array.isArray(z.user.overrides)||z.user.overrides.length||!z.bindings||typeof z.bindings!=='object'||Array.isArray(z.bindings))throw Error('Неподдерживаемое пользовательское хранилище.');
 const p=z.user.preferences;if(!Number.isInteger(p?.selectedSeason)||p.selectedSeason<1950||p.selectedSeason>9999||!['auto','light','dark'].includes(p.theme))throw Error('Неверные настройки.');
 const seen=new Set(),stable=new Set();
 for(const r of z.user.predictions){const b=z.bindings[r?.sessionId];if(!safeId(r?.sessionId)||!Object.hasOwn(z.bindings,r.sessionId)||seen.has(r.sessionId)||!Array.isArray(r.driverIds)||!r.driverIds.length||r.driverIds.length>10||new Set(r.driverIds).size!==r.driverIds.length||r.driverIds.some(id=>typeof id!=='string'||!idPattern.test(id))||typeof r.updatedAt!=='string'||!Number.isFinite(Date.parse(r.updatedAt))||typeof b?.externalEventId!=='string'||!idPattern.test(b.externalEventId)||!Number.isInteger(b.season)||b.season<1950||b.season>9999||b.kind!=='race'||(Object.hasOwn(b,'imported')&&b.imported!==true)||stable.has(b.externalEventId))throw Error('Повреждённый или неоднозначный прогноз.');seen.add(r.sessionId);stable.add(b.externalEventId);}
 if(Object.keys(z.bindings).some(k=>!seen.has(k)))throw Error('Лишние привязки прогнозов.');return z;
}
export function loadStore(storage,year){const raw=storage.getItem(STORAGE_KEY);return raw===null?emptyStore(year):assertStore(JSON.parse(raw));}
export function persistStore(storage,z){assertStore(z);storage.setItem(STORAGE_KEY,JSON.stringify(z));return z;}
export function raceBinding(m,e){
 const matches=m.data.events.filter(x=>x.externalEventId===e.externalEventId);
 const sessions=e.sessions.filter(s=>s.kind==='race');const s=sessions[0];
 if(!e.externalEventId||matches.length!==1||matches[0]!==e||sessions.length!==1||!safeId(s.id)||m.data.events.reduce((n,x)=>n+x.sessions.filter(t=>t.id===s.id).length,0)!==1)return null;
 return {sessionId:s.id,externalEventId:e.externalEventId,season:e.season,kind:'race'};
}
export function getPrediction(z,m,e){const b=raceBinding(m,e);if(!b)return null;const r=z.user.predictions.find(p=>p.sessionId===b.sessionId);const k=z.bindings[b.sessionId];return r&&k&&stableKey(k)===stableKey(b)?r:null;}
export function predictionConflict(z,m,e){const b=raceBinding(m,e);if(!b)return true;return z.user.predictions.some(p=>{const k=z.bindings[p.sessionId];return (p.sessionId===b.sessionId||k.externalEventId===b.externalEventId)&&!(p.sessionId===b.sessionId&&stableKey(k)===stableKey(b));});}
// Date-only schedules conservatively close at UTC midnight before race day (UTC+14 earliest timezone).
export function deadline(e,s){if(typeof s?.scheduledAt==='string'&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(s.scheduledAt)&&Number.isFinite(Date.parse(s.scheduledAt)))return Date.parse(s.scheduledAt);if(!/^\d{4}-\d{2}-\d{2}$/.test(e.date||''))return NaN;return Date.parse(e.date+'T00:00:00Z')-14*3600000;}
export function canEdit(m,e,now=Date.now()){const s=m.session(e,'race'),t=deadline(e,s);return !!raceBinding(m,e)&&e.status==='scheduled'&&s.status==='scheduled'&&!s.results.length&&Number.isFinite(t)&&now<t;}
export function predictionPool(m,e){const ids=m.driverIds(e.season);if(ids.length)return ids;const prev=m.years.filter(y=>y<e.season).at(-1);return prev===undefined?[]:m.driverIds(prev);}
export function savePrediction(z,m,e,ids,now=Date.now()){
 if(!canEdit(m,e,now)||predictionConflict(z,m,e))throw Error('Редактирование недоступно: срок истёк или изменилась привязка этапа.');
 const pool=new Set(predictionPool(m,e));if(!Array.isArray(ids)||ids.length<1||ids.length>10||new Set(ids).size!==ids.length||ids.some(id=>!pool.has(id)))throw Error('Выберите от 1 до 10 разных пилотов из доступного списка.');
 const b=raceBinding(m,e),next=structuredClone(z);next.user.predictions=next.user.predictions.filter(p=>p.sessionId!==b.sessionId);next.user.predictions.push({sessionId:b.sessionId,driverIds:[...ids],updatedAt:new Date(now).toISOString()});next.bindings[b.sessionId]={externalEventId:b.externalEventId,season:b.season,kind:'race'};return assertStore(next);
}
export function removePrediction(z,m,e,now=Date.now()){if(!canEdit(m,e,now)||predictionConflict(z,m,e))throw Error('Редактирование недоступно.');const b=raceBinding(m,e),next=structuredClone(z);next.user.predictions=next.user.predictions.filter(p=>p.sessionId!==b.sessionId);delete next.bindings[b.sessionId];return assertStore(next);}
export function scorePrediction(m,e,p){const s=m.session(e,'race');if(!p||e.status!=='completed'||s?.status!=='final')return null;const pos=new Map(s.results.filter(r=>r.classified===true&&r.started===true&&Number.isInteger(r.position)&&r.position>0).map(r=>[r.driverId,r.position]));if(![1,2,3].every(n=>[...pos.values()].includes(n)))return null;let exact=0,close=0,podium=0;const winner=pos.get(p.driverIds[0])===1;p.driverIds.forEach((id,i)=>{const actual=pos.get(id),expected=i+1;if(actual===expected)exact++;else if(Number.isFinite(actual)&&Math.abs(actual-expected)===1)close++;if(expected<=3&&actual<=3)podium++;});return {exact,close,podium,winner,score:exact*5+close*2+(winner?10:0)+podium*3};}

// Imports restore backups, not proof of timely submission. All changes are staged
// on a clone, and a conflict anywhere aborts the entire operation.
export function mergeImported(current, incoming, model){
 assertStore(current);assertStore(incoming);
 const exact=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
 if(!exact(incoming,['version','user','bindings'])||!exact(incoming.user,['schemaVersion','predictions','overrides','preferences'])||!exact(incoming.user.preferences,['selectedSeason','theme']))throw Error('Неизвестные поля резервной копии.');
 for(const p of incoming.user.predictions){const b=incoming.bindings[p.sessionId];if(!exact(p,['sessionId','driverIds','updatedAt'])||!exact(b,Object.hasOwn(b,'imported')?['externalEventId','season','kind','imported']:['externalEventId','season','kind']))throw Error('Неверная структура прогноза.');}
 const next=structuredClone(current);
 const originalIds=new Map(current.user.predictions.map(p=>[p.sessionId,stableKey(current.bindings[p.sessionId])]));
 const incomingIds=new Map(incoming.user.predictions.map(p=>[p.sessionId,stableKey(incoming.bindings[p.sessionId])]));
 for(const p of incoming.user.predictions){
  const binding=incoming.bindings[p.sessionId],key=stableKey(binding);
  const existing=next.user.predictions.find(q=>next.bindings[q.sessionId].externalEventId===binding.externalEventId);
  const checkId=id=>{for(const index of [originalIds,incomingIds])if(index.has(id)&&index.get(id)!==key)throw Error('Конфликт идентификатора сессии.');if(Object.hasOwn(next.bindings,id)&&stableKey(next.bindings[id])!==key)throw Error('Конфликт идентификатора сессии.');};
  checkId(p.sessionId);
  if(existing&&(stableKey(next.bindings[existing.sessionId])!==key||JSON.stringify(existing.driverIds)!==JSON.stringify(p.driverIds)))throw Error('Конфликт прогноза: '+binding.externalEventId);
  const candidates=model.data.events.filter(e=>e.externalEventId===binding.externalEventId);
  if(candidates.some(e=>e.season!==binding.season))throw Error('Несовместимая привязка этапа.');
  const target=candidates.length===1?raceBinding(model,candidates[0]):null;
  // Missing or ambiguous model identity: preserve original ID; getPrediction
  // requires an unambiguous current model binding, so this stays unattached.
  const id=target?.sessionId??existing?.sessionId??p.sessionId;
  checkId(id);
  if(existing){
   if(existing.sessionId!==id){const old=existing.sessionId;const b=next.bindings[old];delete next.bindings[old];existing.sessionId=id;Object.defineProperty(next.bindings,id,{value:b,enumerable:true,writable:true,configurable:true});}
   // Preserve the original timestamp, ordered picks, and provenance of a local record.
  }else{
   next.user.predictions.push({...structuredClone(p),sessionId:id});
   Object.defineProperty(next.bindings,id,{value:{...structuredClone(binding),imported:true},enumerable:true,writable:true,configurable:true});
  }
 }
 return assertStore(next);
}
