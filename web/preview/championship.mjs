// Transparent Monte Carlo championship estimator. It never changes official data.
// Only full-distance race/sprint outcomes are simulated; see docs/F1_005.md.

const RACE_2000 = [10, 6, 4, 3, 2, 1];
const RACE_2003 = [10, 8, 6, 5, 4, 3, 2, 1];
const RACE_2010 = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
const SPRINT_2021 = [3, 2, 1];
const SPRINT_2022 = [8, 7, 6, 5, 4, 3, 2, 1];

export function scoringRulesForSeason(season) {
  if (!Number.isInteger(season) || season < 2000) throw new Error('Поддерживаются сезоны с 2000 года.');
  const knownThrough = 2026;
  const racePoints = season <= 2002 ? RACE_2000 : season <= 2009 ? RACE_2003 : RACE_2010;
  const sprintPoints = season === 2021 ? SPRINT_2021 : season >= 2022 ? SPRINT_2022 : [];
  const fastestLapBonus = season >= 2019 && season <= 2024;
  const doubleFinalRace = season === 2014;
  const shortenedRacePoints = season === 2026 ? [
    { distance: '2 laps to <25%', points: [6, 4, 3, 2, 1] },
    { distance: '25% to <50%', points: [13, 10, 8, 6, 5, 4, 3, 2, 1] },
    { distance: '50% to <75%', points: [19, 14, 12, 10, 8, 6, 4, 3, 2, 1] },
    { distance: '75% or more', points: RACE_2010 }
  ] : null;
  return {
    season,
    racePoints: [...racePoints],
    sprintPoints: [...sprintPoints],
    fastestLapBonus,
    doubleFinalRace,
    shortenedRacePoints,
    sprintMinDistancePercent: season >= 2022 ? 50 : null,
    verifiedProfile: season <= knownThrough,
    inheritedFrom: season > knownThrough ? knownThrough : null,
    description: season <= 2002 ? '10–6–4–3–2–1' : season <= 2009 ? '10–8–6–5–4–3–2–1' : '25–18–15–12–10–8–6–4–2–1',
    ruleSources: season >= 2026 ? ['https://api.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_02_-_2026-02-27.pdf', 'https://www.fia.com/sites/default/files/final_2026_media_kit.pdf'] : season === 2014 ? ['https://www.planetf1.com/news/explained-f1-points-system-and-how-drivers-earned-points-in-the-past', 'https://www.formula1points.com/psd'] : ['https://www.planetf1.com/news/explained-f1-points-system-and-how-drivers-earned-points-in-the-past']
  };
}

const finite = value => Number.isFinite(value);
const sessionOf = (event, kind) => event?.sessions?.find(s => s.kind === kind);
const keyOfEntry = row => row.entrantId || row.constructorId || row.entityId;
const maxTop = (values, count) => values.slice(0, Math.max(0, count)).reduce((a, b) => a + b, 0);

function latestSnapshot(m, season, kind) {
  return m.snapshots(season, kind).filter(s => Array.isArray(s.rows)).sort((a, b) => b.afterRound - a.afterRound)[0] || null;
}

function remainingSessions(m, season) {
  const sessions = [], blockers = [];
  for (const event of m.eventsOf(season)) {
    if (event.status === 'cancelled') continue;
    for (const kind of ['race', 'sprint']) {
      const session = sessionOf(event, kind);
      if (!session || session.status === 'cancelled') continue;
      if (session.status === 'scheduled' && session.results.length === 0) {
        sessions.push({ event, session, kind });
      } else if (['in_progress', 'partial', 'provisional', 'pending_results'].includes(session.status)) {
        blockers.push(`${event.round}. ${event.name}: ${kind} — ${session.status}`);
      } else if (event.status === 'scheduled' && session.status === 'unavailable') {
        blockers.push(`${event.round}. ${event.name}: ${kind} — нет подтверждённого статуса сессии`);
      }
    }
  }
  return { sessions, blockers };
}

function countbackMaps(m, season) {
  const driver = new Map(), constructor = new Map();
  const ensure = (map, id) => {
    if (!map.has(id)) map.set(id, Array(23).fill(0));
    return map.get(id);
  };
  for (const event of m.eventsOf(season)) {
    if (event.status !== 'completed') continue;
    const race = sessionOf(event, 'race');
    if (race?.status !== 'final') continue;
    for (const row of race.results) {
      if (row.classified !== true || !Number.isInteger(row.position) || row.position < 1) continue;
      ensure(driver, row.driverId)[row.position]++;
      ensure(constructor, keyOfEntry(row))[row.position]++;
    }
  }
  return { driver, constructor };
}

function rosterFromLatestRace(m, season) {
  const events = m.eventsOf(season).filter(e => e.status === 'completed' && sessionOf(e, 'race')?.status === 'final' && sessionOf(e, 'race').results.length);
  const latest = events.at(-1);
  if (!latest) return { latest: null, roster: new Map() };
  const roster = new Map();
  for (const row of sessionOf(latest, 'race').results) {
    if (!row.driverId || !row.constructorId) continue;
    roster.set(row.driverId, { constructorId: row.constructorId, entryKey: keyOfEntry(row), entrantId: row.entrantId || null });
  }
  return { latest, roster };
}

function performanceEstimates(m, season, roster) {
  const stats = new Map([...roster.keys()].map(id => [id, { weighted: 0, weight: 0, starts: 0, nonclassifiedRetirements: 0 }]));
  const events = m.eventsOf(season).filter(e => e.status === 'completed');
  const latestRound = Math.max(1, ...events.map(e => e.round));
  for (const event of events) {
    const age = Math.max(0, latestRound - event.round);
    const decay = Math.pow(0.5, age / 5); // five-round half-life
    const race = sessionOf(event, 'race');
    if (race?.status === 'final') {
      const rows = race.results;
      for (const row of rows) {
        const stat = stats.get(row.driverId);
        if (!stat) continue;
        if (row.started === true) {
          stat.starts++;
          if (['retired', 'not_classified'].includes(row.status) && row.classified === false) stat.nonclassifiedRetirements++;
        }
      }
      const classified = rows.filter(r => r.started === true && r.classified === true && Number.isInteger(r.position) && r.position > 0);
      const field = Math.max(2, classified.length);
      for (const row of classified) {
        const stat = stats.get(row.driverId);
        if (!stat) continue;
        const score = 1 - (row.position - 1) / (field - 1);
        stat.weighted += score * decay * 0.8;
        stat.weight += decay * 0.8;
      }
    }
    const qualifying = sessionOf(event, 'qualifying');
    if (qualifying?.status === 'final') {
      const rows = qualifying.results.filter(r => r.classified === true && Number.isInteger(r.position) && r.position > 0 && stats.has(r.driverId));
      const field = Math.max(2, rows.length);
      for (const row of rows) {
        const stat = stats.get(row.driverId);
        const score = 1 - (row.position - 1) / (field - 1);
        stat.weighted += score * decay * 0.2;
        stat.weight += decay * 0.2;
      }
    }
  }
  const result = new Map();
  for (const [id, stat] of stats) {
    const pace = (stat.weighted + 0.5 * 2.5) / (stat.weight + 2.5); // shrink small samples to neutral
    const strength = Math.max(-1.6, Math.min(1.6, (pace - 0.5) * 3.2));
    const dnfRate = (stat.nonclassifiedRetirements + 0.04 * 8) / (stat.starts + 8);
    result.set(id, { pace, strength, dnfRate, starts: stat.starts, observationsWeight: stat.weight });
  }
  return result;
}

function hashSeed(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0 || 1;
}
function makeRng(seed) {
  let x = seed >>> 0 || 1;
  return () => {
    x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
    return (x >>> 0) / 4294967296;
  };
}
function weightedPick(items, weights, random) {
  let total = weights.reduce((a, b) => a + b, 0);
  let target = random() * total;
  for (let i = 0; i < items.length; i++) {
    target -= weights[i];
    if (target <= 0) return i;
  }
  return Math.max(0, items.length - 1);
}
function plackettLuce(items, strengths, random) {
  const remaining = [...items], ordered = [];
  while (remaining.length) {
    const weights = remaining.map(id => Math.exp(strengths.get(id)?.strength || 0));
    const index = weightedPick(remaining, weights, random);
    ordered.push(remaining[index]);
    remaining.splice(index, 1);
  }
  return ordered;
}
function increment(counts, id, position) {
  if (!counts.has(id)) counts.set(id, Array(23).fill(0));
  counts.get(id)[position]++;
}
function compareByTitle(a, b) {
  if (a.points !== b.points) return b.points - a.points;
  const n = Math.max(a.countback.length, b.countback.length);
  for (let i = 1; i < n; i++) {
    const diff = (b.countback[i] || 0) - (a.countback[i] || 0);
    if (diff) return diff;
  }
  return String(a.name).localeCompare(String(b.name));
}
function sameTitle(a, b) {
  if (a.points !== b.points) return false;
  for (let i = 1; i < Math.max(a.countback.length, b.countback.length); i++) {
    if ((a.countback[i] || 0) !== (b.countback[i] || 0)) return false;
  }
  return true;
}
function makeEntityRows(snapshot, kind, m, countbacks, roster) {
  const rows = new Map();
  for (const row of snapshot.rows) {
    if (!finite(row.points)) throw new Error(`${kind}: отсутствуют опубликованные очки для ${row.entityId}`);
    const id = kind === 'drivers' ? row.entityId : keyOfEntry(row);
    const countback = [...(countbacks.get(id) || Array(23).fill(0))];
    if (finite(row.wins)) countback[1] = row.wins; // published wins are authoritative for the first countback criterion
    rows.set(id, {
      id,
      entityId: row.entityId,
      entrantId: row.entrantId || null,
      name: kind === 'drivers' ? m.driver(row.entityId) : m.team(row.entityId, row.entrantId),
      points: row.points,
      position: row.position ?? null,
      wins: finite(row.wins) ? row.wins : countback[1],
      countback: [...countback],
      active: kind === 'drivers' ? roster.has(id) : false,
      maxFuturePoints: 0
    });
  }
  if (kind === 'drivers') {
    for (const [id] of roster) if (!rows.has(id)) rows.set(id, { id, entityId: id, entrantId: null, name: m.driver(id), points: 0, position: null, wins: 0, countback: countbacks.get(id) || Array(23).fill(0), active: true, maxFuturePoints: 0 });
  } else {
    for (const [entryKey, entry] of new Map([...roster.values()].map(entry => [entry.entryKey, entry]))) {
      if (!rows.has(entryKey)) rows.set(entryKey, { id: entryKey, entityId: entry.constructorId, entrantId: entry.entrantId, name: m.team(entry.constructorId, entry.entrantId), points: 0, position: null, wins: 0, countback: countbacks.get(entryKey) || Array(23).fill(0), active: true, maxFuturePoints: 0 });
    }
  }
  return rows;
}
function sessionMaxForDriver(item, rules, lastRound) {
  if (item.kind === 'sprint') return rules.sprintPoints[0] || 0;
  const multiplier = rules.doubleFinalRace && item.event.round === lastRound ? 2 : 1;
  return (rules.racePoints[0] * multiplier) + (rules.fastestLapBonus ? 1 : 0);
}
function sessionMaxForConstructor(item, rules, lastRound, activeCars) {
  if (item.kind === 'sprint') return maxTop(rules.sprintPoints, activeCars);
  const multiplier = rules.doubleFinalRace && item.event.round === lastRound ? 2 : 1;
  return maxTop(rules.racePoints, activeCars) * multiplier + (rules.fastestLapBonus && activeCars > 0 ? 1 : 0);
}
function mathematicallyClinched(rows) {
  const sorted = [...rows.values()].sort(compareByTitle);
  if (sorted.length < 2) return sorted[0] || null;
  const leader = sorted[0];
  return sorted.slice(1).every(row => leader.points > row.points + row.maxFuturePoints) ? leader : null;
}
function simulateOneSession(ctx, item, random, state) {
  const active = ctx.activeDrivers;
  const finishers = [], retired = [];
  for (const id of active) {
    const model = ctx.performance.get(id) || { strength: 0, dnfRate: 0.04 };
    (random() < model.dnfRate ? retired : finishers).push(id);
  }
  if (!finishers.length && retired.length) {
    retired.sort((a, b) => (ctx.performance.get(b)?.strength || 0) - (ctx.performance.get(a)?.strength || 0));
    finishers.push(retired.shift());
  }
  const ordered = plackettLuce(finishers, ctx.performance, random);
  const pointsTable = item.kind === 'sprint' ? ctx.rules.sprintPoints : ctx.rules.racePoints;
  const multiplier = item.kind === 'race' && ctx.rules.doubleFinalRace && item.event.round === ctx.lastRound ? 2 : 1;
  for (let i = 0; i < ordered.length; i++) {
    const id = ordered[i], base = pointsTable[i] || 0;
    const points = base * multiplier;
    state.driverPoints.set(id, (state.driverPoints.get(id) || 0) + points);
    const entry = ctx.roster.get(id);
    if (entry) state.constructorPoints.set(entry.entryKey, (state.constructorPoints.get(entry.entryKey) || 0) + points);
    if (item.kind === 'race') {
      increment(state.driverCountback, id, i + 1);
      if (entry) increment(state.constructorCountback, entry.entryKey, i + 1);
    }
  }
  if (item.kind === 'race' && ctx.rules.fastestLapBonus && ordered.length) {
    const top = ordered.slice(0, Math.min(10, ordered.length));
    const weights = top.map(id => Math.exp(ctx.performance.get(id)?.strength || 0));
    const winner = top[weightedPick(top, weights, random)];
    state.driverPoints.set(winner, (state.driverPoints.get(winner) || 0) + 1);
    const entry = ctx.roster.get(winner);
    if (entry) state.constructorPoints.set(entry.entryKey, (state.constructorPoints.get(entry.entryKey) || 0) + 1);
  }
}
function titleRows(baseRows, points, counts, winCount) {
  return [...baseRows.values()].map(row => ({
    ...row,
    points: points.get(row.id) ?? row.points,
    countback: counts.get(row.id) || row.countback,
    wins: winCount ? (counts.get(row.id)?.[1] || 0) : row.wins
  }));
}
function probabilities(baseRows, simulations, random, ctx, kind) {
  const titleCounts = new Map([...baseRows.keys()].map(id => [id, 0]));
  const totals = new Map([...baseRows].map(([id, row]) => [id, row.points]));
  for (let sim = 0; sim < simulations; sim++) {
    const state = {
      driverPoints: new Map([...ctx.driverBase].map(([id, row]) => [id, row.points])),
      constructorPoints: new Map([...ctx.constructorBase].map(([id, row]) => [id, row.points])),
      driverCountback: new Map([...ctx.driverBase].map(([id, row]) => [id, [...row.countback]])),
      constructorCountback: new Map([...ctx.constructorBase].map(([id, row]) => [id, [...row.countback]]))
    };
    for (const item of ctx.remaining) simulateOneSession(ctx, item, random, state);
    const points = kind === 'drivers' ? state.driverPoints : state.constructorPoints;
    const counts = kind === 'drivers' ? state.driverCountback : state.constructorCountback;
    const scored = titleRows(baseRows, points, counts, true).sort(compareByTitle);
    const tied = scored.filter(row => sameTitle(row, scored[0]));
    const share = 1 / tied.length;
    for (const row of tied) titleCounts.set(row.id, (titleCounts.get(row.id) || 0) + share);
    for (const [id, row] of baseRows) totals.set(id, (totals.get(id) || row.points) + ((points.get(id) ?? row.points) - row.points));
  }
  return [...baseRows.values()].map(row => ({
    ...row,
    expectedFinalPoints: totals.get(row.id) / simulations,
    probability: (titleCounts.get(row.id) || 0) / simulations * 100
  })).sort((a, b) => b.probability - a.probability || b.expectedFinalPoints - a.expectedFinalPoints || a.name.localeCompare(b.name));
}

export function simulateChampionship(m, season, options = {}) {
  const simulations = options.simulations ?? 10000;
  if (!Number.isInteger(simulations) || simulations < 100 || simulations > 100000) throw new Error('Число симуляций должно быть от 100 до 100 000.');
  const rules = scoringRulesForSeason(season);
  const events = m.eventsOf(season);
  if (!events.length) return { status: 'unavailable', season, message: 'Нет данных выбранного сезона.' };
  const driverSnapshot = latestSnapshot(m, season, 'drivers');
  const constructorSnapshot = latestSnapshot(m, season, 'constructors');
  if (!driverSnapshot || !constructorSnapshot) return { status: 'unavailable', season, message: 'Нет обоих опубликованных снимков зачёта.' };
  if (driverSnapshot.afterRound !== constructorSnapshot.afterRound) return { status: 'blocked', season, message: 'Личный зачёт и Кубок конструкторов имеют разные последние этапы.' };
  const remainingInfo = remainingSessions(m, season);
  if (remainingInfo.blockers.length) return { status: 'blocked', season, message: 'Есть сессии с неполными или неоднозначными данными.', blockers: remainingInfo.blockers };
  const remaining = remainingInfo.sessions;
  if (!remaining.length) return { status: 'complete', season, message: 'В сезоне нет запланированных гонок или спринтов без результатов.' };
  if (!rules.verifiedProfile) return { status: 'blocked', season, message: `Регламент ${season} года не подтверждён. Используется профиль ${rules.inheritedFrom} года только как кандидат; расчёт заблокирован до проверки FIA.` };
  const { latest, roster } = rosterFromLatestRace(m, season);
  if (!latest || roster.size < 2) return { status: 'blocked', season, message: 'Не удалось определить состав участников по последней завершённой гонке.' };
  const counts = countbackMaps(m, season);
  const driverBase = makeEntityRows(driverSnapshot, 'drivers', m, counts.driver, roster);
  const constructorBase = makeEntityRows(constructorSnapshot, 'constructors', m, counts.constructor, roster);
  for (const row of constructorBase.values()) row.activeCars = [...roster.values()].filter(entry => entry.entryKey === row.id).length;
  const performance = performanceEstimates(m, season, roster);
  const activeDrivers = [...roster.keys()];
  const lastRound = Math.max(...events.map(e => e.round));
  for (const row of driverBase.values()) {
    row.maxFuturePoints = row.active ? remaining.reduce((sum, item) => sum + sessionMaxForDriver(item, rules, lastRound), 0) : 0;
  }
  for (const row of constructorBase.values()) {
    row.maxFuturePoints = remaining.reduce((sum, item) => sum + sessionMaxForConstructor(item, rules, lastRound, row.activeCars), 0);
  }
  const driverClinched = mathematicallyClinched(driverBase);
  const constructorClinched = mathematicallyClinched(constructorBase);
  const seedText = `${season}|${driverSnapshot.afterRound}|${driverSnapshot.rows.map(r => `${r.entityId}:${r.points}`).join(',')}|${remaining.map(x => x.session.id).join(',')}`;
  const seed = options.seed ?? hashSeed(seedText);
  const ctx = { rules, remaining, lastRound, roster, performance, activeDrivers, driverBase, constructorBase };
  const driverRows = driverClinched
    ? [...driverBase.values()].map(row => ({ ...row, expectedFinalPoints: null, probability: row.id === driverClinched.id ? 100 : 0 })).sort((a,b)=>b.probability-a.probability||b.points-a.points)
    : probabilities(driverBase, simulations, makeRng(seed ^ 0x9e3779b9), ctx, 'drivers');
  const constructorRows = constructorClinched
    ? [...constructorBase.values()].map(row => ({ ...row, expectedFinalPoints: null, probability: row.id === constructorClinched.id ? 100 : 0 })).sort((a,b)=>b.probability-a.probability||b.points-a.points)
    : probabilities(constructorBase, simulations, makeRng(seed ^ 0x85ebca6b), ctx, 'constructors');
  const raceCount = remaining.filter(x => x.kind === 'race').length;
  const sprintCount = remaining.filter(x => x.kind === 'sprint').length;
  const warnings = [
    'Состав участников будущих этапов взят из последней завершённой гонки; неподтверждённые замены пилотов не моделируются.',
    'Модель использует результаты гонок (80%) и квалификаций (20%) текущего сезона, с уменьшением веса старых этапов и сглаживанием малых выборок.',
    'Симуляция предполагает полную дистанцию. Красные флаги, сокращённые дистанции, штрафы, погода, Safety Car и особенности конкретной трассы отдельно не моделируются.',
    'Это статистическая оценка, а не официальный прогноз FIA или Formula 1.'
  ];
  if (!sprintCount) warnings.push('До конца сезона спринтовых сессий с ожидаемыми результатами нет.');
  if (rules.shortenedRacePoints) warnings.push('Регламент содержит отдельную шкалу очков для сокращённой гонки; текущая симуляция использует полную дистанцию.');
  return {
    status: 'ok', season, simulations: driverClinched && constructorClinched ? 0 : simulations,
    currentAfterRound: driverSnapshot.afterRound,
    remaining: { races: raceCount, sprints: sprintCount, sessions: remaining.length },
    scoring: rules,
    model: { method: 'Plackett–Luce Monte Carlo', raceWeight: 0.8, qualifyingWeight: 0.2, recencyHalfLifeRounds: 5, reliabilityPrior: 0.04, reliabilityPriorStarts: 8 },
    rosterSource: `${latest.id} · ${latest.name}`,
    mathematicallyClinched: { drivers: driverClinched?.id || null, constructors: constructorClinched?.id || null },
    drivers: driverRows.map(({countback, active, maxFuturePoints, ...row}) => ({...row, active, maxFuturePoints})),
    constructors: constructorRows.map(({countback, activeCars, maxFuturePoints, ...row}) => ({...row, activeCars, maxFuturePoints})),
    warnings
  };
}

// Conservative UI-only title marker: no Monte Carlo, no assumed roster, no countback guess.
// Only latest published standings can receive a marker; earlier snapshots must not leak the final champion.
export function standingTitle(m, season, kind, snapshot) {
  if (!snapshot || snapshot!==m.standing(season,kind)) return null;
  const events=m.eventsOf(season).filter(e=>e.status!=='cancelled');
  if (!events.length) return null;
  const leader=snapshot.rows.find(r=>r.position===1);
  if (!leader || snapshot.rows.filter(r=>r.position===1).length!==1 || !finite(leader.points)) return null;
  const completed=events.filter(e=>e.status==='completed' && sessionOf(e,'race')?.status==='final');
  if (!completed.length || snapshot.afterRound!==Math.max(...completed.map(e=>e.round))) return null;
  if (events.every(e=>completed.includes(e)&&!e.sessions.some(s=>s.kind==='sprint'&& !['final','cancelled'].includes(s.status)))) return {id:leader.entrantId||leader.entityId,status:'final'};
  if (season<2000 || !scoringRulesForSeason(season).verifiedProfile) return null;
  const rules=scoringRulesForSeason(season), remaining=remainingSessions(m,season);
  if (remaining.blockers.length || !remaining.sessions.length) return null;
  // Missing race/sprint results must not silently lower the maximum.
  if (events.some(e=>!completed.includes(e)&&(e.status!=='scheduled'||sessionOf(e,'race')?.status!=='scheduled'||sessionOf(e,'race')?.results?.length!==0))) return null;
  if (events.some(e=>e.sessions.some(s=>s.kind==='sprint'&&(completed.includes(e)?!['final','cancelled'].includes(s.status):!['scheduled','cancelled'].includes(s.status)||s.status==='scheduled'&&s.results?.length!==0)))) return null;
  if (remaining.sessions.some(x=>x.event.round<=snapshot.afterRound)) return null;
  const lastRound=Math.max(...events.map(e=>e.round));
  const maximum=remaining.sessions.reduce((sum,item)=>sum+(kind==='drivers'?sessionMaxForDriver(item,rules,lastRound):sessionMaxForConstructor(item,rules,lastRound,2)),0);
  const rivals=snapshot.rows.filter(r=>r!==leader);
  if (rivals.some(r=>!finite(r.points)))return null;
  // Include a potential new entry starting from zero, and all rivals regardless of latest roster.
  return leader.points>maximum && rivals.every(r=>leader.points>r.points+maximum)?{id:leader.entrantId||leader.entityId,status:'clinched'}:null;
}
