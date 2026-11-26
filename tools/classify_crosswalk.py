"""Summarize existing crosswalk report without rewriting source records or approving aliases."""
import argparse
from collections import Counter
from pathlib import Path
from validate_data import read
from import_f1db import write_new

def classify(d):
    a,b=d['primary'],d['secondary'];field=d['field']
    if field=='qualifyingTimesMs' and isinstance(a,list) and isinstance(b,list):
        # Only old single-session vs Q1 padded representation is equivalent.
        if len(a)==1 and b==[a[0],None,None] or len(b)==1 and a==[b[0],None,None]:return 'single_session_time_format'
    if field=='position' and (a is None or b is None):return 'classification_review'
    if a is None or b is None:return 'missing_value'
    if field=='timeMs' and isinstance(a,int) and isinstance(b,int) and abs(a-b)==1:return 'one_millisecond_review'
    return 'value_conflict'

def summarize(report):
    groups=Counter();details=[]
    for d in report['differences']:
        category=classify(d);groups[category]+=1;details.append(dict(d,category=category))
    return dict(scope='classification of reported differences only; no independent verification',comparedRows=report['comparedRows'],differenceCount=len(details),categories=dict(groups),differences=details,unmatchedRows=report['unmatchedRows'],publicationAuthorized=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--report',required=True);a=p.parse_args()
    try:
        if Path(a.input).resolve()==Path(a.report).resolve():raise ValueError('distinct input and output required')
        r=summarize(read(a.input));write_new(a.report,r)
        for k,v in sorted(r['categories'].items()):print(f'{k}: {v}')
        print(f"Unmatched rows: {len(r['unmatchedRows'])}; not release authorization");return 0
    except (ValueError,OSError,KeyError) as e:print('CLASSIFICATION FAILED:',e);return 1
if __name__=='__main__':raise SystemExit(main())
