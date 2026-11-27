import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildModel} from '../web/preview/model.mjs';
import {scoringRulesForSeason,simulateChampionship} from '../web/preview/championship.mjs';

function fixture({season=2026, clinched=false, sprint=true, partial=false}={}) {
  const d=JSON.parse(readFileSync(new URL('../examples/synthetic-dataset.json',import.meta.url)));
  d.datasetStatus='draft';
  d.drivers.push(
    {id:'test:c',name:'Test C',aliases:[],sourceIds:['test:sample'],givenName:null,familyName:null,birthDate:null,nationality:null},
    {id:'test:d',name:'Test D',aliases:[],sourceIds:['test:sample'],givenName:null,familyName:null,birthDate:null,nationality:null}
  );
  d.constructors.push(
    {id:'test:team2',name:'Test Team 2',aliases:[],sourceIds:['test:sample'],nationality:null,lineageId:null}
  );
  const e=d.events[0]; e.season=season;e.id=`${season}-R01`;e.sessions[0].id=`${season}-R01-race`;
  const r=e.sessions[0].results;
  r[0].position=1;r[0].positionText='1';r[0].points=25;r[0].constructorId='test:team';
  r[1].position=2;r[1].positionText='2';r[1].points=18;r[1].constructorId='test:team';
  r.push(
    {driverId:'test:c',constructorId:'test:team2',position:3,positionText:'3',points:15,started:true,classified:true,status:'finished',rawStatus:'Finished',laps:50,gridPosition:3,timeMs:null,gapMs:null,qualifyingTimesMs:null},
    {driverId:'test:d',constructorId:'test:team2',position:4,positionText:'4',points:12,started:true,classified:true,status:'finished',rawStatus:'Finished',laps:50,gridPosition:4,timeMs:null,gapMs:null,qualifyingTimesMs:null}
  );
  const standingsDrivers=clinched
    ? [{entityId:'test:a',position:1,positionText:'1',points:402,wins:9},{entityId:'test:b',position:2,positionText:'2',points:304,wins:4},{entityId:'test:c',position:3,positionText:'3',points:200,wins:1},{entityId:'test:d',position:4,positionText:'4',points:100,wins:0}]
    : [{entityId:'test:a',position:1,positionText:'1',points:50,wins:1},{entityId:'test:b',position:2,positionText:'2',points:48,wins:0},{entityId:'test:c',position:3,positionText:'3',points:40,wins:0},{entityId:'test:d',position:4,positionText:'4',points:30,wins:0}];
  const standingsConstructors=clinched
    ? [{entityId:'test:team',position:1,positionText:'1',points:666,wins:12},{entityId:'test:team2',position:2,positionText:'2',points:300,wins:2}]
    : [{entityId:'test:team',position:1,positionText:'1',points:98,wins:1},{entityId:'test:team2',position:2,positionText:'2',points:70,wins:0}];
  d.standings=[{season,afterRound:1,kind:'drivers',sourceIds:['test:sample'],rows:standingsDrivers},{season,afterRound:1,kind:'constructors',sourceIds:['test:sample'],rows:standingsConstructors}];
  const makeFuture=(round,withSprint=false)=>({id:`${season}-R${String(round).padStart(2,'0')}`,season,round,name:`Future GP ${round}`,circuitId:'test:track',date:`${season}-12-${String(round+1).padStart(2,'0')}`,status:'scheduled',sourceIds:['test:sample'],externalEventId:`test:race${round}`,grandPrixKey:`test:gp${round}`,sessions:[
    {id:`${season}-R${String(round).padStart(2,'0')}-race`,kind:'race',status:partial?'partial':'scheduled',scheduledAt:null,sourceIds:['test:sample'],results:[]},
    ...(withSprint?[{id:`${season}-R${String(round).padStart(2,'0')}-sprint`,kind:'sprint',status:'scheduled',scheduledAt:null,sourceIds:['test:sample'],results:[]}]:[])
  ]});
  d.events.push(makeFuture(2,sprint),makeFuture(3,false));
  return d;
}

test('season scoring profiles cover historical changes and sprint eras',()=>{
  assert.deepEqual(scoringRulesForSeason(2000).racePoints,[10,6,4,3,2,1]);
  assert.deepEqual(scoringRulesForSeason(2003).racePoints,[10,8,6,5,4,3,2,1]);
  assert.equal(scoringRulesForSeason(2014).doubleFinalRace,true);
  assert.equal(scoringRulesForSeason(2019).fastestLapBonus,true);
  assert.deepEqual(scoringRulesForSeason(2021).sprintPoints,[3,2,1]);
  assert.deepEqual(scoringRulesForSeason(2022).sprintPoints,[8,7,6,5,4,3,2,1]);
  assert.equal(scoringRulesForSeason(2024).fastestLapBonus,true);
  assert.equal(scoringRulesForSeason(2025).fastestLapBonus,false);
  assert.equal(scoringRulesForSeason(2026).fastestLapBonus,false);
});

test('2026 partial-distance rule table is preserved but not simulated',()=>{
  const rules=scoringRulesForSeason(2026);
  assert.deepEqual(rules.shortenedRacePoints.map(x=>x.points),[[6,4,3,2,1],[13,10,8,6,5,4,3,2,1],[19,14,12,10,8,6,4,3,2,1],[25,18,15,12,10,8,6,4,2,1]]);
});

test('future seasons inherit latest known rules but are blocked pending FIA review',()=>{
  const rules=scoringRulesForSeason(2027);
  assert.equal(rules.verifiedProfile,false);assert.equal(rules.inheritedFrom,2026);
  const result=simulateChampionship(buildModel(fixture({season:2027})),2027,{simulations:100});
  assert.equal(result.status,'blocked');assert.match(result.message,/не подтверждён/);
});

test('remaining races and sprint are detected separately',()=>{
  const result=simulateChampionship(buildModel(fixture()),2026,{simulations:1000,seed:42});
  assert.equal(result.status,'ok');assert.deepEqual(result.remaining,{races:2,sprints:1,sessions:3});
});

test('Monte Carlo probabilities are deterministic for a fixed seed and sum to 100',()=>{
  const m=buildModel(fixture());
  const a=simulateChampionship(m,2026,{simulations:3000,seed:12345});
  const b=simulateChampionship(m,2026,{simulations:3000,seed:12345});
  assert.deepEqual(a.drivers.map(x=>x.probability),b.drivers.map(x=>x.probability));
  assert.deepEqual(a.constructors.map(x=>x.probability),b.constructors.map(x=>x.probability));
  assert.ok(Math.abs(a.drivers.reduce((s,x)=>s+x.probability,0)-100)<1e-8);
  assert.ok(Math.abs(a.constructors.reduce((s,x)=>s+x.probability,0)-100)<1e-8);
  assert.ok(a.drivers.every(x=>Number.isFinite(x.expectedFinalPoints)));
});

test('mathematically clinched driver and constructor are exact without Monte Carlo',()=>{
  const result=simulateChampionship(buildModel(fixture({clinched:true,sprint:false})),2026,{simulations:5000});
  assert.equal(result.status,'ok');assert.equal(result.simulations,0);
  assert.equal(result.mathematicallyClinched.drivers,'test:a');
  assert.equal(result.mathematicallyClinched.constructors,'test:team');
  assert.equal(result.drivers[0].probability,100);assert.equal(result.constructors[0].probability,100);
});

test('partial or provisional remaining sessions block forecast',()=>{
  const result=simulateChampionship(buildModel(fixture({partial:true})),2026,{simulations:100});
  assert.equal(result.status,'blocked');assert.ok(result.blockers.length);
});

test('completed season returns no forecast',()=>{
  const d=fixture({sprint:false});
  d.events=d.events.filter(e=>e.round===1);
  const result=simulateChampionship(buildModel(d),2026,{simulations:100});
  assert.equal(result.status,'complete');
});

test('unsupported season and simulation count are rejected',()=>{
  assert.throws(()=>scoringRulesForSeason(1999));
  assert.throws(()=>simulateChampionship(buildModel(fixture()),2026,{simulations:99}));
  assert.throws(()=>simulateChampionship(buildModel(fixture()),2026,{simulations:100001}));
});

test('team maximum points reflect two-car constructor scoring',()=>{
  const result=simulateChampionship(buildModel(fixture()),2026,{simulations:100});
  const team=result.constructors.find(x=>x.id==='test:team');
  assert.equal(team.activeCars,2);
  assert.equal(team.maxFuturePoints,101); // two race P1+P2 and sprint P1+P2
});

test('2014 final race double points are included in maximum future points',()=>{
  const d=fixture({season:2014,sprint:false});
  const result=simulateChampionship(buildModel(d),2014,{simulations:100});
  const driver=result.drivers.find(x=>x.id==='test:a');
  const team=result.constructors.find(x=>x.id==='test:team');
  assert.equal(driver.maxFuturePoints,75); // 25 + 2*25
  assert.equal(team.maxFuturePoints,129); // 43 + 2*43
});

test('fastest-lap bonus increases maximum race points only in 2019–2024',()=>{
  const d=fixture({season:2024,sprint:false});
  const result=simulateChampionship(buildModel(d),2024,{simulations:100});
  assert.equal(result.drivers.find(x=>x.id==='test:a').maxFuturePoints,52); // two races, +1 each
  assert.equal(result.constructors.find(x=>x.id==='test:team').maxFuturePoints,88); // 44 per race
});

test('2021 sprint point cap is three for a driver and five for two constructor cars',()=>{
  const d=fixture({season:2021,sprint:true});
  const result=simulateChampionship(buildModel(d),2021,{simulations:100});
  assert.equal(result.drivers.find(x=>x.id==='test:a').maxFuturePoints,55); // two race wins + fastest-lap bonus + one sprint
  assert.equal(result.constructors.find(x=>x.id==='test:team').maxFuturePoints,93); // two race P1/P2 + fastest-lap bonus + sprint P1/P2
});

test('forecast calculation never mutates the official candidate',()=>{
  const d=fixture(),before=JSON.stringify(d);
  simulateChampionship(buildModel(d),2026,{simulations:1000,seed:9876});
  assert.equal(JSON.stringify(d),before);
});
