// Read-only model for the local preview. Never infer points from position.
export function buildModel(data) {
  if (data.schemaVersion !== '2.0.0' || data.datasetStatus !== 'draft' || !Array.isArray(data.events) || !data.events.length) throw Error('Требуется непустая локальная база v2 со статусом draft');
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
export function seasonPairs(m,y){
  const map=new Map();
  for(const e of m.eventsOf(y).filter(m.completed))for(const k of ['race','qualifying']){
    const groups=new Map();
    for(const r of m.session(e,k)?.results||[]){const entry=r.entrantId||r.constructorId;if(!groups.has(entry))groups.set(entry,[]);groups.get(entry).push(r);}
    for(const [entry,rows] of groups)for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
      const [a,b]=[rows[i],rows[j]].sort((a,b)=>a.driverId.localeCompare(b.driverId));if(a.driverId===b.driverId)continue;
      const key=JSON.stringify([entry,a.driverId,b.driverId]);if(!map.has(key))map.set(key,{entry,constructorId:a.constructorId,entrantId:a.entrantId,a:a.driverId,b:b.driverId,race:{a:0,b:0,tie:0,skipped:0},qualifying:{a:0,b:0,tie:0,skipped:0}});
      const v=map.get(key)[k];if(!comparable(a)||!comparable(b)||(k==='race'&&(a.started!==true||b.started!==true)))v.skipped++;else if(a.position<b.position)v.a++;else if(b.position<a.position)v.b++;else v.tie++;
    }
  }
  return [...map.values()].sort((a,b)=>m.team(a.constructorId,a.entrantId).localeCompare(m.team(b.constructorId,b.entrantId))||m.driver(a.a).localeCompare(m.driver(b.a))||m.driver(a.b).localeCompare(m.driver(b.b)));
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
