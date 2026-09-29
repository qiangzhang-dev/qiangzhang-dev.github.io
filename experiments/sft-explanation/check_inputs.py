"""Independent invariants that matter for interpreting the paired experiment."""
import argparse,json
from pathlib import Path
from transformers import AutoTokenizer
from experiment import ROOT,build_data,encode,score

train,test=build_data()
assert train==json.loads((ROOT/'data/train.json').read_text())
assert test==json.loads((ROOT/'data/test.json').read_text())
assert len({r['id'] for r in train+test})==144
assert not ({r['question'] for r in train}&{r['question'] for r in test})
for r in train+test:
    p=r['id'].split('-')
    if p[0]=='inventory':
        _,boxes,each,given=p
        assert sum([int(each)]*int(boxes))-int(given)==r['answer']
    elif p[0]=='discount':
        _,goods,shipping,threshold=p
        assert r['answer']==(20 if int(goods)>=int(threshold) else 0)
    elif p[0]=='percentage':
        _,initial,pct=p
        from fractions import Fraction
        assert Fraction(int(initial))*(1+Fraction(int(pct),100))*(1-Fraction(int(pct),100))==r['answer']
for r in train:
    assert score(r['explained'])==score(r['answer_only'])==r['answer']
assert score('The inputs are 20 and 10; I do not know.') is None
assert score('Answer: 20. Answer: 0.') is None
assert score('Answer: 96.0')==96
p=argparse.ArgumentParser()
p.add_argument('--model-dir',default=str(ROOT.parent/'sft-model-cache'))
args=p.parse_args()
tok=AutoTokenizer.from_pretrained(args.model_dir,local_files_only=True)
counts={}
for arm in ['explained','answer_only']:
    total=0
    for r in train:
        ids,labels=encode(tok,r,arm)
        first=next(i for i,x in enumerate(labels) if x!=-100)
        assert all(x==-100 for x in labels[:first])
        assert 'assistant' in tok.decode(ids[:first])
        target=tok.decode(ids[first:])
        assert target.startswith(r[arm]) and tok.eos_token in target
        total+=len(ids)-first
    counts[arm]=total
print(json.dumps({'data_and_mask_checks':'passed','supervised_tokens_per_epoch':counts}))
