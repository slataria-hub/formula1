"""Create a NEW empty user file; never read or migrate legacy predictions."""
import argparse
from pathlib import Path
from validate_data import read, validate
from import_f1db import write_new


def empty_user(data):
    if not data['events']:
        raise ValueError('nonempty official calendar required')
    user={'schemaVersion':'2.0.0','predictions':[],'overrides':[],
          'preferences':{'selectedSeason':max(e['season'] for e in data['events']),'theme':'auto'}}
    errors=validate(data,user)
    if errors:
        raise ValueError('validation failed: '+str(errors[:5]))
    return user


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('official');p.add_argument('--output',required=True);a=p.parse_args()
    try:
        if Path(a.official).resolve()==Path(a.output).resolve():raise ValueError('distinct output required')
        write_new(a.output,empty_user(read(a.official)))
        print('PASS empty user file created; no legacy migration');return 0
    except (OSError,ValueError,KeyError) as e:print('INIT FAILED:',e);return 1

if __name__=='__main__':raise SystemExit(main())
