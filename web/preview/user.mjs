// Browser-only user state. Never mutate the official dataset or read the legacy data.json.
export const STORAGE_KEY='f1-analytics:v2:user:1';
const idPattern=/^[a-z][a-z0-9_-]*:[A-Za-z0-9_.-]+$/;
export function emptyStore(year){return {version:1,user:{schemaVersion:'2.0.0',predictions:[],overrides:[],preferences:{selectedSeason:year,theme:'auto'}},bindings:{}};}
export function assertStore(z){
 if(!z||z.version!==1||z.user?.schemaVersion!=='2.0.0'||!Array.isArray(z.user.predictions)||!Array.isArray(z.user.overrides)||z.user.overrides.length||!z.bindings||typeof z.bindings!=='object'||Array.isArray(z.bindings))throw Error('Неподдерживаемое пользовательское хранилище.');
 const p=z.user.preferences;if(!Number.isInteger(p?.selectedSeason)||p.selectedSeason<1950||p.selectedSeason>9999||!['auto','light','dark'].includes(p.theme))throw Error('Неверные настройки.');
 const seen=new Set(),stable=new Set();
 for(const r of z.user.predictions){const b=z.bindings[r?.sessionId];if(typeof r?.sessionId!=='string'||!r.sessionId||seen.has(r.sessionId)||!Array.isArray(r.driverIds)||!r.driverIds.length||r.driverIds.length>10||new Set(r.driverIds).size!==r.driverIds.length||r.driverIds.some(id=>typeof id!=='string'||!idPattern.test(id))||typeof r.updatedAt!=='string'||!Number.isFinite(Date.parse(r.updatedAt))||typeof b?.externalEventId!=='string'||!idPattern.test(b.externalEventId)||!Number.isInteger(b.season)||b.kind!=='race'||stable.has(b.externalEventId))throw Error('Повреждённый или неоднозначный прогноз.');seen.add(r.sessionId);stable.add(b.externalEventId);}
 if(Object.keys(z.bindings).some(k=>!seen.has(k)))throw Error('Лишние привязки прогнозов.');return z;
}
export function loadStore(storage,year){const raw=storage.getItem(STORAGE_KEY);return raw===null?emptyStore(year):assertStore(JSON.parse(raw));}
export function persistStore(storage,z){assertStore(z);storage.setItem(STORAGE_KEY,JSON.stringify(z));return z;}
export function raceBinding(m,e){const s=m.session(e,'race');return s&&e.externalEventId?{sessionId:s.id,externalEventId:e.externalEventId,season:e.season,kind:'race'}:null;}
export function getPrediction(z,m,e){const b=raceBinding(m,e);if(!b)return null;const r=z.user.predictions.find(p=>p.sessionId===b.sessionId);const k=z.bindings[b.sessionId];return r&&k?.externalEventId===b.externalEventId&&k.season===b.season?r:null;}
export function predictionConflict(z,m,e){const b=raceBinding(m,e);if(!b)return true;return z.user.predictions.some(p=>{const k=z.bindings[p.sessionId];return (p.sessionId===b.sessionId||k.externalEventId===b.externalEventId)&&!(p.sessionId===b.sessionId&&k.externalEventId===b.externalEventId&&k.season===b.season);});}
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
