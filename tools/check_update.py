"""Offline update safety gate; does not publish or migrate user data."""
import argparse
from validate_data import read,validate

def check_update(old,new,user=None):
    errors=['old: '+e for e in validate(old)]+['new: '+e for e in validate(new,user)]
    if errors:return errors
    for key in ('drivers','constructors','circuits'):
        a={r['id']:r for r in old[key]};b={r['id']:r for r in new[key]}
        for k,r in a.items():
            if k not in b:errors.append(f'{key}: removed ID {k}');continue
            old_alias={(x['provider'],x['externalId']) for x in r['aliases']};new_alias={(x['provider'],x['externalId']) for x in b[k]['aliases']}
            if not old_alias<=new_alias:errors.append(f'{key}: lost alias {k}')
            if key=='drivers' and (r.get('birthDate') and r.get('birthDate')!=b[k].get('birthDate')):errors.append(f'driver identity changed {k}')
    a={e['id']:e for e in old['events']};b={e['id']:e for e in new['events']}
    for k,e in a.items():
        n=b.get(k)
        if not n:errors.append(f'event removed {k}');continue
        if any(e.get(f) and e[f]!=n.get(f) for f in ('externalEventId','grandPrixKey')) or (not e.get('grandPrixKey') and (e['name'],e['circuitId'])!=(n['name'],n['circuitId'])):
            errors.append(f'event identity changed at {k}; calendar migration required')
        if e['status']=='completed' and n['status']!='completed':errors.append(f'completed event regressed {k}')
        ns={s['kind']:s for s in n['sessions']}
        for s in e['sessions']:
            t=ns.get(s['kind'])
            if not t:errors.append(f'session removed {s["id"]}');continue
            if s['status']=='final' and t['status']!='final':errors.append(f'final session regressed {s["id"]}')
            if {r['driverId'] for r in s['results']}-{r['driverId'] for r in t['results']}:errors.append(f'participants removed {s["id"]}')
    for key,fields in [('standings',('season','afterRound','kind')),('entrants',('id',)),('adjustments',('season','afterRound','kind','entityId','pointsDelta'))]:
        before={tuple(r[f] for f in fields) for r in old.get(key,[])};after={tuple(r[f] for f in fields) for r in new.get(key,[])}
        for x in before-after:errors.append(f'{key}: removed {x}')
    return errors

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('old');p.add_argument('new');p.add_argument('--user');a=p.parse_args()
    try:errors=check_update(read(a.old),read(a.new),read(a.user) if a.user else None)
    except (OSError,ValueError,KeyError) as e:errors=[str(e)]
    for e in errors:print('BLOCK:',e)
    print('BLOCKED' if errors else 'PASS update compatibility only; publication not authorized')
    return int(bool(errors))
if __name__=='__main__':raise SystemExit(main())
