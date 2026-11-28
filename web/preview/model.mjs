// Read-only model for the local preview. Never infer points from position.
export function buildModel(data) {
  if (data.schemaVersion !== '2.0.0' || !['draft','verified'].includes(data.datasetStatus) || !Array.isArray(data.events) || !data.events.length) throw Error('Требуется непустая локальная база v2 со статусом draft или verified');
  const index = arr => new Map(arr.map(x=>[x.id,x]));
  const drivers=index(data.drivers), teams=index(data.constructors), circuits=index(data.circuits), entrants=index(data.entrants||[]);
  const events=index(data.events), sources=index(data.sources);
  const years=[...new Set(data.events.map(e=>e.season))].sort((a,b)=>a-b);
  const eventsOf=y=>data.events.filter(e=>e.season===y).sort((a,b)=>a.round-b.round);
  const snapshots=(y,k)=>data.standings.filter(s=>s.season===y&&s.kind===k).sort((a,b)=>a.afterRound-b.afterRound);
  const standing=(y,k,r)=>{const a=snapshots(y,k);return r==null?a.at(-1):a.find(s=>s.afterRound===r);};
  const name=(map,id)=>map.get(id)?.name??id??'—';
  const driver=id=>name(drivers,id), team=(id,entrantId)=>entrants.has(entrantId)?name(entrants,entrantId):name(teams,id);
  const session=(e,k)=>e.sessions.find(s=>s.kind===k);
  const completed=e=>e.status==='completed';
  const points=(e,id)=>{const rr=e.sessions.filter(s=>s.kind==='race'||s.kind==='sprint').flatMap(s=>s.results).filter(r=>r.driverId===id);return rr.length?rr.some(r=>r.points==null)?null:rr.reduce((a,r)=>a+r.points,0):null;};
  const driverIds=y=>[...new Set([...eventsOf(y).flatMap(e=>e.sessions.flatMap(s=>s.results.map(r=>r.driverId))),...snapshots(y,'drivers').flatMap(s=>s.rows.map(r=>r.entityId))])];
  return {data,drivers,teams,circuits,entrants,events,sources,years,eventsOf,snapshots,standing,driver,team,session,completed,points,driverIds};
}
export const num=v=>v==null?'—':String(v).replace('.',',');
export const place=r=>r.position==null?((r.positionText && !/^\d+$/.test(r.positionText))?r.positionText:'—'):String(r.position);
export function time(ms) {if(ms==null)return '—';const h=Math.floor(ms/3600000),m=Math.floor(ms/60000)%60,s=Math.floor(ms/1000)%60;return (h?`${h}:${String(m).padStart(2,'0')}`:String(m))+':'+String(s).padStart(2,'0')+'.'+String(ms%1000).padStart(3,'0');}
export const sessionNames={race:'Гонка',qualifying:'Квалификация',sprint:'Спринт',sprint_qualifying:'Спринт-квалификация',grid:'Стартовая решётка',practice:'Тренировка'};
export const statuses={completed:'Завершён',scheduled:'Запланирован',in_progress:'Идёт',cancelled:'Отменён',unknown:'Статус неизвестен',final:'Результаты',provisional:'Предварительно',partial:'Неполные данные',pending_results:'Ожидаются результаты',unavailable:'Нет данных у источника',finished:'Финиш',retired:'Сход',dns:'Не стартовал',dsq:'Дисквалификация',excluded:'Исключён',not_classified:'Не классифицирован'};
export function stats(m,y){const es=m.eventsOf(y),done=es.filter(m.completed);return {events:es.length,completed:done.length,qualifying:done.filter(e=>m.session(e,'qualifying')?.results.length).length,sprints:es.filter(e=>m.session(e,'sprint')?.results.length).length,drivers:m.driverIds(y).length};}
export function pairs(m,e){const rows=m.session(e,'race')?.results||[],groups=new Map();for(const r of rows){const k=r.entrantId||r.constructorId;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}return [...groups.values()];}

// H2H counts only directly comparable classified results in the same session and entry.
export function comparable(r){return r?.classified===true && Number.isInteger(r.position) && r.position>0;}
const h2hEntry=r=>JSON.stringify([r.constructorId,r.entrantId||null]);
export const pairKey=p=>JSON.stringify([p.constructorId,p.entrantId||null,p.a,p.b]);
export function headToHeadResult(s,p,k){
  if(!s||s.status!=='final')return {outcome:'absent',a:null,b:null};
  const rows=s.results.filter(r=>r.constructorId===p.constructorId&&(r.entrantId||null)===(p.entrantId||null));
  const aa=rows.filter(r=>r.driverId===p.a),bb=rows.filter(r=>r.driverId===p.b);
  const a=aa.length===1?aa[0]:null,b=bb.length===1?bb[0]:null;
  if(!aa.length||!bb.length)return {outcome:'absent',a,b};
  const valid=r=>comparable(r)&&!['dns','dsq','excluded','withdrawn','not_classified'].includes(r.status)&&(k==='qualifying'||r.started===true);
  return {a,b,outcome:!valid(a)||!valid(b)?'skipped':a.position<b.position?'a':b.position<a.position?'b':'tie'};
}
export function pairTimeline(m,y,p){
  const totals={race:{a:0,b:0,tie:0,skipped:0},qualifying:{a:0,b:0,tie:0,skipped:0},sprint:{a:0,b:0,tie:0,skipped:0}};
  const rows=m.eventsOf(y).filter(m.completed).map(e=>{
    const row={eventId:e.id,round:e.round,name:e.name};
    for(const k of Object.keys(totals)){const r=headToHeadResult(m.session(e,k),p,k);if(r.outcome!=='absent')totals[k][r.outcome]++;row[k]={...r,total:{...totals[k]}};}
    return row;
  });
  return {rows,totals};
}
export function seasonPairs(m,y){
  const map=new Map();
  for(const e of m.eventsOf(y).filter(m.completed))for(const k of ['race','qualifying','sprint']){
    const s=m.session(e,k);if(s?.status!=='final')continue;
    const groups=new Map();
    for(const r of s.results){const entry=h2hEntry(r);if(!groups.has(entry))groups.set(entry,[]);groups.get(entry).push(r);}
    for(const rows of groups.values())for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
      const [a,b]=[rows[i],rows[j]].sort((a,b)=>a.driverId.localeCompare(b.driverId));if(a.driverId===b.driverId)continue;
      const p={entry:a.entrantId||a.constructorId,constructorId:a.constructorId,entrantId:a.entrantId,a:a.driverId,b:b.driverId};map.set(pairKey(p),p);
    }
  }
  return [...map.values()].map(p=>({...p,...pairTimeline(m,y,p).totals})).sort((a,b)=>m.team(a.constructorId,a.entrantId).localeCompare(m.team(b.constructorId,b.entrantId))||m.driver(a.a).localeCompare(m.driver(b.a))||m.driver(a.b).localeCompare(m.driver(b.b)));
}
export function driverStats(m,y){
 const rows=new Map(m.driverIds(y).map(id=>[id,{id,starts:0, wins:0,podiums:0,poles:0,fastest:0,retired:0}]));
 for(const e of m.eventsOf(y).filter(m.completed)){
  const race=m.session(e,'race');for(const r of race?.results||[]){const s=rows.get(r.driverId);if(r.started===true){s.starts++;if(r.status==='retired')s.retired++;}if(comparable(r)&&r.started===true){if(r.position===1)s.wins++;if(r.position<=3)s.podiums++;}}
  for(const r of m.session(e,'qualifying')?.results||[])if(comparable(r)&&r.position===1)rows.get(r.driverId).poles++;
  for(const f of m.data.fastestLaps||[])if(f.sessionId===race?.id&&rows.has(f.driverId))rows.get(f.driverId).fastest++;
 }
 const points=new Map((m.standing(y,'drivers')?.rows||[]).map(r=>[r.entityId,r.points]));return [...rows.values()].map(r=>({...r,points:points.get(r.id)??null}));
}
export function eventSummary(m,e){const race=m.session(e,'race'),q=m.session(e,'qualifying');const winner=race?.results.find(r=>comparable(r)&&r.position===1),pole=q?.results.find(r=>comparable(r)&&r.position===1);return {winner,pole,circuit:m.circuits.get(e.circuitId)};}
export function displayDate(date){if(!/^\d{4}-\d{2}-\d{2}$/.test(date||''))return date||'—';return `${date.slice(8,10)}.${date.slice(5,7)}.${date.slice(0,4)}`;}

// Published snapshots are authoritative; missing snapshots remain gaps, not zeroes.
export function championshipSeries(m,y,ids){
 const rounds=m.eventsOf(y).map(e=>({round:e.round,name:e.name}));
 const snapshots=new Map(m.snapshots(y,'drivers').map(s=>[s.afterRound,new Map(s.rows.map(r=>[r.entityId,r]))]));
 return {rounds,series:[...new Set(ids)].filter(id=>m.driverIds(y).includes(id)).map(id=>({id,name:m.driver(id),values:rounds.map(e=>{const r=snapshots.get(e.round)?.get(id);return {points:Number.isFinite(r?.points)?r.points:null,position:Number.isInteger(r?.position)&&r.position>0?r.position:null};})}))};
}
export function chartSegments(values,metric){
 const segments=[];let part=[];
 values.forEach((v,i)=>{if(Number.isFinite(v[metric]))part.push({i,value:v[metric]});else if(part.length){segments.push(part);part=[];}});
 if(part.length)segments.push(part);return segments;
}
export function defaultComparison(m,y){const ids=m.driverIds(y),ranked=(m.standing(y,'drivers')?.rows||[]).map(r=>r.entityId);return [...new Set([...ranked,...ids])].filter(id=>ids.includes(id)).slice(0,2);}

// Published order; unranked/excluded rows and shared positions are not invented into adjacent ranks.
export function adjacentStandingGaps(rows){return rows.map((r,i)=>{const p=rows[i-1];return i>0&&Number.isInteger(r.position)&&Number.isInteger(p.position)&&r.position>0&&p.position>0&&r.position>=p.position&&Number.isFinite(r.points)&&Number.isFinite(p.points)?Number((r.points-p.points).toFixed(9)):null;});}

// Final classification only; never promote P4 to a missing podium slot.
export function sessionPodium(s){
  if(!s||s.status!=='final'||!['race','sprint'].includes(s.kind))return [];
  const rows=s.results.filter(r=>comparable(r)&&r.started===true&&!['dns','dsq','excluded','withdrawn','not_classified'].includes(r.status)&&r.position<=3);
  return [1,2,3].map(p=>{const matches=rows.filter(r=>r.position===p);return matches.length===1&&rows.filter(r=>r.driverId===matches[0].driverId).length===1?matches[0]:null;});
}
// Grid position 0 means pit-lane/unknown; no numeric delta in that case.
export function positionGain(r){
  return comparable(r)&&r.started===true&&!['dns','dsq','excluded','withdrawn','not_classified'].includes(r.status)&&Number.isInteger(r.gridPosition)&&r.gridPosition>0?r.gridPosition-r.position:null;
}
export function defaultEventKind(e){return e.sessions.some(s=>s.kind==='race')?'race':e.sessions[0]?.kind||'race';}

// F1-007.5: descriptive season analytics, never a prediction model.
export function dashboardStats(m,y){
 const events=m.eventsOf(y),done=events.filter(m.completed),final=(e,k)=>{const s=m.session(e,k);return s?.status==='final'&&s.results.length?s:null;};
 const rows=new Map(m.driverIds(y).map(id=>[id,{id,points:null,starts:0,wins:0,podiums:0,poles:0,fastest:0,retired:0}]));
 const points=m.standing(y,'drivers'),teams=m.standing(y,'constructors');
 for(const r of points?.rows||[])if(rows.has(r.entityId)&&Number.isFinite(r.points))rows.get(r.entityId).points=r.points;
 const recent=done.slice(-5).map(e=>({eventId:e.id,round:e.round,name:e.name,race:final(e,'race')}));
 let races=0,qualifying=0,sprints=0,winners=0,poles=0,fastest=0;
 const valid=r=>comparable(r)&&!['dns','dsq','excluded','withdrawn','not_classified'].includes(r.status);
 const unique=s=>s.results.filter(r=>s.results.filter(x=>x.driverId===r.driverId).length===1);
 for(const e of done){
  const r=final(e,'race'),q=final(e,'qualifying');
  if(r){races++;const rr=unique(r);for(const v of rr)if(v.started===true&&rows.has(v.driverId)){const a=rows.get(v.driverId);a.starts++;if(v.status==='retired')a.retired++;}
   const pod=sessionPodium(r).map(v=>v&&rr.includes(v)?v:null);for(const v of pod)if(v&&rows.has(v.driverId)){rows.get(v.driverId).podiums++;}if(pod[0]&&rows.has(pod[0].driverId)){rows.get(pod[0].driverId).wins++;winners++;}
   const laps=(m.data.fastestLaps||[]).filter(f=>f.sessionId===r.id);if(laps.length===1&&rr.some(v=>v.driverId===laps[0].driverId&&v.started===true)&&rows.has(laps[0].driverId)){rows.get(laps[0].driverId).fastest++;fastest++;}
  }
  if(q){qualifying++;const p=q.results.filter(v=>valid(v)&&v.position===1);if(p.length===1&&unique(q).includes(p[0])&&rows.has(p[0].driverId)){rows.get(p[0].driverId).poles++;poles++;}}
  if(final(e,'sprint'))sprints++;
 }
 const ranked=[...rows.values()].sort((a,b)=>(b.points??-Infinity)-(a.points??-Infinity)||m.driver(a.id).localeCompare(m.driver(b.id)));
 const form=ranked.map(a=>{const values=recent.map(e=>{const rr=e.race?.results.filter(r=>r.driverId===a.id)||[];return rr.length===1&&rr[0].started===true&&Number.isFinite(rr[0].points)?rr[0].points:null;});const samples=values.filter(Number.isFinite);return {id:a.id,values,count:samples.length,total:samples.length?samples.reduce((a,b)=>a+b,0):null};});
 const teamRows=(teams?.rows||[]).filter(r=>Number.isInteger(r.position)&&r.position>0&&Number.isFinite(r.points)).sort((a,b)=>a.position-b.position);
 return {events:events.length,completed:done.length,cancelled:events.filter(e=>e.status==='cancelled').length,races,qualifying,sprints,winners,poles,fastest,drivers:ranked,teamRows,driverRound:points?.afterRound??null,teamRound:teams?.afterRound??null,recent:recent.map(({race,...e})=>e),form};
}
