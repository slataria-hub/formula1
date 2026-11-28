import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildModel} from '../web/preview/model.mjs';
import {STORAGE_KEY,emptyStore,assertStore,loadStore,persistStore,deadline,canEdit,predictionPool,getPrediction,predictionConflict,savePrediction,removePrediction,scorePrediction} from '../web/preview/user.mjs';
const now=Date.parse('2026-01-01T12:00:00Z');
function fixture(){const d=JSON.parse(readFileSync(new URL('../examples/synthetic-dataset.json',import.meta.url)));d.datasetStatus='draft';const first=d.events[0];first.externalEventId='test:race1';const e=structuredClone(first);Object.assign(e,{id:'2026-R02',externalEventId:'test:race2',round:2,date:'2026-01-03',status:'scheduled'});Object.assign(e.sessions[0],{id:'2026-R02-race',status:'scheduled',results:[],scheduledAt:'2026-01-03T14:00:00Z'});d.events.push(e);return {d,e,m:buildModel(d)};}
const storage=()=>{const map=new Map();return {getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v)};};
test('fresh storage is empty, with no legacy migration',()=>{const s=storage();s.setItem('data',JSON.stringify({predictions:['legacy']}));assert.deepEqual(loadStore(s,2027),emptyStore(2027));});
test('save ordered forecast separately and persist roundtrip',()=>{const {d,e,m}=fixture(),before=JSON.stringify(d),z=emptyStore(2026),s=storage();const next=savePrediction(z,m,e,['test:b','test:a'],now);assert.equal(z.user.predictions.length,0);assert.equal(JSON.stringify(d),before);persistStore(s,next);assert.deepEqual(getPrediction(loadStore(s,2026),m,e).driverIds,['test:b','test:a']);});
test('duplicate or unknown drivers and empty prediction rejected',()=>{const {m,e}=fixture();for(const ids of [[],['test:a','test:a'],['test:unknown']])assert.throws(()=>savePrediction(emptyStore(2026),m,e,ids,now));});
test('deadline is exact if given, conservative date-only otherwise',()=>{const {m,e}=fixture(),s=e.sessions[0];const t=deadline(e,s);assert.equal(t,Date.parse(s.scheduledAt));assert.equal(canEdit(m,e,t-1),true);assert.equal(canEdit(m,e,t),false);s.scheduledAt=null;assert.equal(deadline(e,s),Date.parse('2026-01-02T10:00:00Z'));assert.equal(canEdit(m,e,deadline(e,s)),false);});
test('completed, cancelled, unknown date and partial results cannot be edited',()=>{const {m,e}=fixture();for(const status of ['completed','cancelled','in_progress']){e.status=status;assert.equal(canEdit(m,e,now),false);}e.status='scheduled';e.sessions[0].status='partial';assert.equal(canEdit(m,e,now),false);e.sessions[0].status='scheduled';e.sessions[0].scheduledAt=null;e.date=null;assert.equal(canEdit(m,e,now),false);});
test('different external event with same round blocks stale forecast',()=>{const {m,e}=fixture();const z=savePrediction(emptyStore(2026),m,e,['test:a'],now);e.externalEventId='test:other';assert.equal(getPrediction(z,m,e),null);assert.equal(predictionConflict(z,m,e),true);assert.throws(()=>savePrediction(z,m,e,['test:a'],now));});
test('renumbering of same external event preserves old data and blocks ambiguous attachment',()=>{const {m,e}=fixture();const z=savePrediction(emptyStore(2026),m,e,['test:a'],now);e.sessions[0].id='2026-R03-race';assert.equal(predictionConflict(z,m,e),true);assert.equal(getPrediction(z,m,e),null);assert.equal(z.user.predictions.length,1);});
test('rescheduling same stable IDs retains prediction',()=>{const {m,e}=fixture();const z=savePrediction(emptyStore(2026),m,e,['test:a'],now);e.date='2026-01-04';assert.deepEqual(getPrediction(z,m,e).driverIds,['test:a']);});
test('delete only before deadline, keeps source store intact',()=>{const {m,e}=fixture();const z=savePrediction(emptyStore(2026),m,e,['test:a'],now);assert.throws(()=>removePrediction(z,m,e,deadline(e,e.sessions[0])));assert.equal(removePrediction(z,m,e,now).user.predictions.length,0);assert.equal(z.user.predictions.length,1);});
test('future season with no observed drivers uses previous season as provisional pool',()=>{const {d,e}=fixture();e.season=2027;const m=buildModel(d);assert.deepEqual(predictionPool(m,e),['test:a','test:b']);});
test('legacy scoring uses official final classified finish, not array index',()=>{const {m,e}=fixture();e.status='completed';const s=e.sessions[0];s.status='final';s.results=[{driverId:'test:c',position:3,classified:true,started:true},{driverId:'test:a',position:1,classified:true,started:true},{driverId:'test:b',position:2,classified:true,started:true}];assert.deepEqual(scorePrediction(m,e,{driverIds:['test:a','test:c','test:b']}),{exact:1,close:2,podium:3,winner:true,score:28});s.status='partial';assert.equal(scorePrediction(m,e,{driverIds:['test:a']}),null);s.status='final';s.results[0].classified=false;assert.equal(scorePrediction(m,e,{driverIds:['test:a']}),null);});
test('corrupted store not silently overwritten and storage failure propagated',()=>{const s=storage();s.setItem(STORAGE_KEY,'bad JSON');assert.throws(()=>loadStore(s,2026));assert.equal(s.getItem(STORAGE_KEY),'bad JSON');assert.throws(()=>persistStore({setItem(){throw Error('quota');}},emptyStore(2026)));const z=emptyStore(2026);z.bindings.foo={};assert.throws(()=>assertStore(z));});

test('import remaps stable event, deduplicates and never overwrites conflicting picks',async()=>{const {mergeImported}=await import('../web/preview/user.mjs');const {m,e}=fixture(),initial=emptyStore(2026),incoming=savePrediction(initial,m,e,['test:a'],now);e.sessions[0].id='2026-R03-race';const next=mergeImported(initial,incoming,m);assert.equal(next.user.predictions[0].sessionId,'2026-R03-race');assert.equal(initial.user.predictions.length,0);assert.deepEqual(mergeImported(next,incoming,m),next);const conflict=structuredClone(incoming);conflict.user.predictions[0].driverIds=['test:b'];assert.throws(()=>mergeImported(next,conflict,m));assert.throws(()=>mergeImported(next,{},m));});

// R-03: exact production regression, plus transaction and provenance checks.
import {mergeImported} from '../web/preview/user.mjs';
test('R-03 existing old session is rebound, incoming date does not replace original',()=>{
 const {m,e}=fixture();e.sessions[0].id='old-race';const current=savePrediction(emptyStore(2026),m,e,['test:b','test:a'],now);
 e.sessions[0].id='new-race';const incoming=savePrediction(emptyStore(2026),m,e,['test:b','test:a'],now+1000);
 const before=structuredClone(current),input=structuredClone(incoming),next=mergeImported(current,incoming,m);
 assert.deepEqual(current,before);assert.deepEqual(incoming,input);assert.equal(next.user.predictions.length,1);
 assert.deepEqual(getPrediction(next,m,e),{sessionId:'new-race',driverIds:['test:b','test:a'],updatedAt:new Date(now).toISOString()});
 assert.equal(Object.hasOwn(next.bindings,'old-race'),false);assert.equal(next.bindings['new-race'].imported,undefined);
 assert.deepEqual(mergeImported(next,incoming,m),next);assert.deepEqual(mergeImported(next,current,m),next);
});
test('R-03 order conflict aborts without mutating inputs, even after staged addition',()=>{
 const {m,e,d}=fixture();const current=savePrediction(emptyStore(2026),m,e,['test:a','test:b'],now);
 const incoming=savePrediction(emptyStore(2026),m,e,['test:b','test:a'],now);
 const extra=structuredClone(incoming.user.predictions[0]);extra.sessionId='missing-race';incoming.user.predictions.unshift(extra);incoming.bindings['missing-race']={externalEventId:'test:missing',season:2027,kind:'race'};
 const c=structuredClone(current),i=structuredClone(incoming),official=structuredClone(d);
 assert.throws(()=>mergeImported(current,incoming,m),/Конфликт/);assert.deepEqual(current,c);assert.deepEqual(incoming,i);assert.deepEqual(d,official);
});
test('R-03 inconsistent season or session kind is rejected',()=>{
 const {m,e}=fixture(),current=savePrediction(emptyStore(2026),m,e,['test:a'],now);
 const incoming=structuredClone(current);incoming.bindings[e.sessions[0].id].season=2027;
 assert.throws(()=>mergeImported(current,incoming,m));assert.throws(()=>mergeImported(emptyStore(2026),incoming,m));
 incoming.bindings[e.sessions[0].id].season=2026;incoming.bindings[e.sessions[0].id].kind='sprint';assert.throws(()=>mergeImported(current,incoming,m));
});
test('R-03 session identifier collision with another forecast aborts transaction',()=>{
 const {m,e}=fixture(),current=savePrediction(emptyStore(2026),m,e,['test:a'],now);
 const incoming=structuredClone(current);incoming.bindings[e.sessions[0].id].externalEventId='test:missing';
 assert.throws(()=>mergeImported(current,incoming,m),/Конфликт идентификатора/);
 const other=structuredClone(current);const id=e.sessions[0].id;other.user.predictions[0].sessionId='occupied';other.bindings.occupied={externalEventId:'test:missing',season:2026,kind:'race'};delete other.bindings[id];e.sessions[0].id='occupied';
 assert.throws(()=>mergeImported(other,current,m),/Конфликт идентификатора/);
});
test('R-03 missing or ambiguous event retained unattached, no duplicate on repeat',()=>{
 const {m,e,d}=fixture();const incoming=savePrediction(emptyStore(2026),m,e,['test:a'],now);const eventId=e.externalEventId;
 e.externalEventId='test:other';let next=mergeImported(emptyStore(2026),incoming,m);assert.equal(next.user.predictions.length,1);assert.equal(getPrediction(next,m,e),null);assert.deepEqual(mergeImported(next,incoming,m),next);
 e.externalEventId=eventId;const dupe=structuredClone(e);dupe.id='ambiguous';dupe.sessions[0].id='ambiguous-race';d.events.push(dupe);
 next=mergeImported(emptyStore(2026),incoming,m);assert.equal(getPrediction(next,m,e),null);assert.equal(getPrediction(next,m,dupe),null);assert.deepEqual(mergeImported(next,incoming,m),next);
 d.events.pop();assert.deepEqual(getPrediction(next,m,e).driverIds,['test:a']);
});
test('R-03 imported historical record is retrospective and cannot be edited or deleted',()=>{
 const {m,e}=fixture();const incoming=savePrediction(emptyStore(2026),m,e,['test:a'],now);e.status='completed';e.sessions[0].status='final';
 const current=emptyStore(2025);current.user.preferences.theme='dark';const next=mergeImported(current,incoming,m),id=e.sessions[0].id;
 assert.equal(next.bindings[id].imported,true);assert.deepEqual(next.user.preferences,current.user.preferences);assert.equal(getPrediction(next,m,e).updatedAt,new Date(now).toISOString());
 assert.throws(()=>savePrediction(next,m,e,['test:b'],now));assert.throws(()=>removePrediction(next,m,e,now));assert.deepEqual(mergeImported(next,next,m),next);
 const tampered=structuredClone(next);tampered.bindings[id].imported=false;assert.throws(()=>mergeImported(current,tampered,m));
});
