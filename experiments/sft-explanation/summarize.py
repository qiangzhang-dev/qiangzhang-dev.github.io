"""Produce descriptive results; no significance or broad capability claims."""
import collections,html,json,statistics
from pathlib import Path
from experiment import ROOT,dump

r=ROOT/'results'
assert (r/'complete.json').exists(), 'Full run has not finished'
tags=['baseline','explained-seed17','answer_only-seed17','explained-seed29','answer_only-seed29']
data={tag:json.loads((r/f'{tag}.json').read_text()) for tag in tags}
ids=[x['id'] for x in data['baseline']['records']]
assert all([x['id'] for x in d['records']]==ids for d in data.values())
summary=[]
for tag,d in data.items():
    row={'tag':tag,'seconds':d['seconds']}
    for group in ['within_template','probe']:
        records=[x for x in d['records'] if (x['task']=='probe')==(group=='probe')]
        row[group]={'n':len(records),'correct':sum(x['correct'] for x in records),
            'unparsed':sum(x['parsed'] is None for x in records),'hit_limit':sum(x['hit_limit'] for x in records),
            'mean_generated_tokens':statistics.mean(x['generated_tokens'] for x in records)}
    row['tasks']={task:{'n':sum(x['task']==task for x in d['records']),
        'correct':sum(x['correct'] for x in d['records'] if x['task']==task)} for task in ['discount','inventory','percentage','probe']}
    if tag!='baseline':
        training=json.loads((r/f'{tag}-training.json').read_text())
        row['training']={k:training[k] for k in ['steps','supervised_tokens','seconds','trainable_parameters','adapter_l1_change']}
        base=data['baseline']['records']
        row['versus_baseline']={'improved':[x['id'] for b,x in zip(base,d['records']) if not b['correct'] and x['correct']],
            'regressed':[x['id'] for b,x in zip(base,d['records']) if b['correct'] and not x['correct']]}
    summary.append(row)
pairs=[]
for seed in [17,29]:
    a=data[f'explained-seed{seed}']['records'];b=data[f'answer_only-seed{seed}']['records']
    pairs.append({'seed':seed,'explained_only_correct':[x['id'] for x,y in zip(a,b) if x['correct'] and not y['correct']],
        'answer_only_correct':[x['id'] for x,y in zip(a,b) if y['correct'] and not x['correct']]})
dump(r/'summary.json',{'models':summary,'paired_disagreements':pairs})
print(json.dumps(summary,ensure_ascii=False,indent=2))

import runpy
runpy.run_path(str(ROOT/'render_report.py'))
