#!/usr/bin/env node
import {readFile,writeFile} from 'node:fs/promises';
import {buildModel} from '../web/preview/model.mjs';
import {simulateChampionship} from '../web/preview/championship.mjs';
const input=process.argv[2], simulations=Number(process.argv[3]||1000), output=process.argv[4];
if(!input){console.error('Usage: node tools/backtest_championship.mjs official.json [simulations] [report.json]');process.exit(1);}
const source=JSON.parse(await readFile(input,'utf8'));
if(source.datasetStatus!=='draft')throw new Error('Backtest accepts draft candidates only.');
const cases=[];
for(let year=2000;year<=2025;year++){
 const seasonEvents=source.events.filter(e=>e.season===year).sort((a,b)=>a.round-b.round);
 if(seasonEvents.length<4)continue;
 const cutoffEvent=seasonEvents.at(-3),cutoff=cutoffEvent.round;
 const data=structuredClone(source);
 for(const e of data.events.filter(e=>e.season===year&&e.round>cutoff)){
  e.status='scheduled';
  for(const s of e.sessions){
   if(['race','sprint'].includes(s.kind)){s.status='scheduled';s.results=[];}
  }
 }
 data.standings=data.standings.filter(s=>s.season!==year||s.afterRound<=cutoff);
 const model=buildModel(data),forecast=simulateChampionship(model,year,{simulations,seed:year*7919});
 const finalDriver=source.standings.filter(s=>s.season===year&&s.kind==='drivers').sort((a,b)=>b.afterRound-a.afterRound)[0];
 const finalConstructor=source.standings.filter(s=>s.season===year&&s.kind==='constructors').sort((a,b)=>b.afterRound-a.afterRound)[0];
 const actualDriver=finalDriver?.rows.slice().sort((a,b)=>(a.position??999)-(b.position??999)||b.points-a.points)[0];
 const actualConstructor=finalConstructor?.rows.slice().sort((a,b)=>(a.position??999)-(b.position??999)||b.points-a.points)[0];
 const driver=forecast.drivers?.find(x=>x.id===actualDriver?.entityId);
 const constructor=forecast.constructors?.find(x=>x.id===(actualConstructor?.entrantId||actualConstructor?.entityId));
 const brier=(rows,actual)=>rows?.reduce((sum,row)=>sum+Math.pow((row.probability||0)/100-(row.id===actual?1:0),2),0)??null;
 cases.push({season:year,cutoffRound:cutoff,remaining:forecast.remaining,status:forecast.status,driverChampion:actualDriver?.entityId,driverChampionProbability:driver?.probability??null,driverTopPrediction:forecast.drivers?.[0]?.id??null,driverTopProbability:forecast.drivers?.[0]?.probability??null,driverBrier:brier(forecast.drivers,actualDriver?.entityId),constructorChampion:actualConstructor?.entrantId||actualConstructor?.entityId,constructorChampionProbability:constructor?.probability??null,constructorTopPrediction:forecast.constructors?.[0]?.id??null,constructorTopProbability:forecast.constructors?.[0]?.probability??null,constructorBrier:brier(forecast.constructors,actualConstructor?.entrantId||actualConstructor?.entityId),driverClinched:forecast.mathematicallyClinched?.drivers??null,constructorClinched:forecast.mathematicallyClinched?.constructors??null,message:forecast.message??null});
}
const driverOpen=cases.filter(c=>!c.driverClinched),constructorOpen=cases.filter(c=>!c.constructorClinched);
const report={scope:'historical two-round holdout; exploratory model validation only',datasetStatus:source.datasetStatus,simulationsPerCase:simulations,cases,driverTop1:countTop1(cases,'driver'),constructorTop1:countTop1(cases,'constructor'),driverNonClinchedCases:driverOpen.length,constructorNonClinchedCases:constructorOpen.length,driverNonClinchedTop1:countTop1(driverOpen,'driver'),constructorNonClinchedTop1:countTop1(constructorOpen,'constructor'),meanActualDriverChampionProbability:mean(cases.map(c=>c.driverChampionProbability)),meanActualConstructorChampionProbability:mean(cases.map(c=>c.constructorChampionProbability)),meanNonClinchedDriverChampionProbability:mean(driverOpen.map(c=>c.driverChampionProbability)),meanNonClinchedConstructorChampionProbability:mean(constructorOpen.map(c=>c.constructorChampionProbability)),meanDriverBrier:mean(cases.map(c=>c.driverBrier)),meanConstructorBrier:mean(cases.map(c=>c.constructorBrier)),meanNonClinchedDriverBrier:mean(driverOpen.map(c=>c.driverBrier)),meanNonClinchedConstructorBrier:mean(constructorOpen.map(c=>c.constructorBrier))};
function countTop1(rows,kind){const actual=kind==='driver'?'driverChampion':'constructorChampion',top=kind==='driver'?'driverTopPrediction':'constructorTopPrediction';return rows.filter(r=>r[actual]&&r[actual]===r[top]).length;}
function mean(values){const a=values.filter(Number.isFinite);return a.length?a.reduce((x,y)=>x+y,0)/a.length:null;}
const text=JSON.stringify(report,null,2)+'\n';
if(output)await writeFile(output,text,{flag:'wx'});else process.stdout.write(text);
console.error(`BACKTEST: ${cases.length} seasons; driver top-1 ${report.driverTop1}; constructor top-1 ${report.constructorTop1}`);
