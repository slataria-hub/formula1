#!/usr/bin/env node
import {readFile, writeFile} from 'node:fs/promises';
import {buildModel} from '../web/preview/model.mjs';
import {simulateChampionship} from '../web/preview/championship.mjs';

function args(argv) {
  const out={input:null,season:null,simulations:10000,output:null,seed:undefined};
  for(let i=2;i<argv.length;i++){
    const key=argv[i];
    if(key==='--season')out.season=Number(argv[++i]);
    else if(key==='--simulations')out.simulations=Number(argv[++i]);
    else if(key==='--output')out.output=argv[++i];
    else if(key==='--seed')out.seed=Number(argv[++i]);
    else if(!out.input)out.input=key;
    else throw new Error('Неизвестный аргумент: '+key);
  }
  if(!out.input||!Number.isInteger(out.season))throw new Error('Использование: node tools/forecast_championship.mjs official.json --season 2026 [--simulations 10000] [--output report.json]');
  return out;
}
try{
  const a=args(process.argv),data=JSON.parse(await readFile(a.input,'utf8'));
  if(data.datasetStatus!=='draft')throw new Error('Разрешён только локальный кандидат draft; публикация запрещена.');
  const result=simulateChampionship(buildModel(data),a.season,{simulations:a.simulations,seed:a.seed});
  const json=JSON.stringify({generatedAt:new Date().toISOString(),datasetStatus:data.datasetStatus,publicationAuthorized:false,...result},null,2)+'\n';
  if(a.output)await writeFile(a.output,json,{flag:'wx'}); else process.stdout.write(json);
  if(result.status==='ok'){
    console.error(`${a.season}: ${result.remaining.races} races, ${result.remaining.sprints} sprints; driver champion: ${result.mathematicallyClinched.drivers||'Monte Carlo'}; constructor champion: ${result.mathematicallyClinched.constructors||'Monte Carlo'}`);
    process.exitCode=0;
  }else{
    console.error(`FORECAST ${result.status}: ${result.message}`);process.exitCode=2;
  }
}catch(e){console.error('FORECAST FAILED:',e.message);process.exitCode=1;}
