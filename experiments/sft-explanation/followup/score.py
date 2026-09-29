"""Separate explicit Answer parsing from final numerical correctness.

Extraction never receives the expected answer. Unresolved cases require a saved,
quoted review; a missing review is an error when --complete is requested.
"""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TAGS=['baseline','explained-seed17','answer_only-seed17','explained-seed29','answer_only-seed29']
NUMBER=r'-?\d+(?:,\d{3})*(?:\.\d+)?'
# Allowed suffix after a final number: units and closing markup, but no new claim.
TAIL=re.compile(r'^[\s.*$%`\\\[\](){}:;!?,"\']*(?:(?:dollars?|pencils?|pencils? remain|pencils? left|remaining|remain|left|centimeters?|cm|days?|months?|sides?|minutes?|hours?)[\s.*$%`\\\[\](){}:;!?,"\']*)?$',re.I)

def numeric(s):return float(s.replace(',',''))
def extract(text):
    explicit=list(re.finditer(r'(?i)(?:\*\*)?\banswer(?:\*\*)?\s*:\s*(?:\*\*)?\s*\$?\s*('+NUMBER+r')',text))
    if explicit:
        vals={numeric(m[1]) for m in explicit};last=explicit[-1]
        if len(vals)==1 and TAIL.fullmatch(text[last.end():]):
            return dict(value=numeric(last[1]),method='terminal_answer_field',quote=text[last.start():].strip())
        return None
    boxed=list(re.finditer(r'\\boxed\{\s*('+NUMBER+r')\s*\}',text))
    if boxed:
        last=boxed[-1]
        if TAIL.fullmatch(text[last.end():]):
            return dict(value=numeric(last[1]),method='terminal_boxed_number',quote=text[last.start():].strip())
    # A closing declarative statement, not an arbitrary last number.
    closing=list(re.finditer(r'(?i)\b(?:is|are|equals)\s+(?:\*\*|\$|`)*('+NUMBER+r')',text))
    if closing:
        last=closing[-1]
        if TAIL.fullmatch(text[last.end():]):
            return dict(value=numeric(last[1]),method='terminal_numerical_statement',quote=text[last.start():].strip())
    return None

def run(require_complete=False):
    reviewfile=ROOT/'reviews.json'
    reviews=json.loads(reviewfile.read_text()) if reviewfile.exists() else {}
    records=[];pending=[];files={}
    for tag in TAGS:
      for variant in ['original','reworded']:
        path=ROOT/'results'/f'{tag}-{variant}.json'
        if not path.exists():
            if require_complete:raise AssertionError(f'Missing {path.name}')
            continue
        files[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        for raw in json.loads(path.read_text())['records']:
            key=f'{tag}/{variant}/{raw["id"]}'
            decision=extract(raw['output'])
            terminal_answer=decision is not None and decision['method']=='terminal_answer_field'
            if raw['hit_limit']:
                decision=dict(value=None,method='incomplete_at_512',quote=raw['output'][-180:])
            elif key in reviews:
                manual=reviews[key]
                assert manual['quote'] in raw['output'],f'Quote mismatch: {key}'
                assert manual['reason'],f'Reason missing: {key}'
                decision=dict(value=manual['value'],method='documented_review',quote=manual['quote'],reason=manual['reason'])
            if decision is None:
                pending.append(dict(key=key,question=raw['question'],output=raw['output']))
                continue
            records.append(dict(key=key,tag=tag,variant=variant,id=raw['id'],task=raw['task'],expected=raw['expected'],
                terminal_answer_format=terminal_answer,legacy_answer_parsed=raw['parsed'] is not None,legacy_correct=raw['correct'],hit_limit=raw['hit_limit'],
                final_value=decision['value'],value_correct=decision['value']==raw['expected'],decision=decision))
    (ROOT/'pending_reviews.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n')
    if require_complete:assert not pending,f'{len(pending)} unresolved reviews'
    result=dict(version='final-value-v1',scope='Final numerical value, not all reasoning steps or full instruction compliance.',
        raw_sha256=files,records=records,pending_count=len(pending))
    (ROOT/'scored.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'records_scored':len(records),'pending':len(pending),'cells_loaded':len(files)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--complete',action='store_true');a=p.parse_args();run(a.complete)
