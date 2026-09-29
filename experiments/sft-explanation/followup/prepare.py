"""Freeze reworded test inputs before generating follow-up responses."""
import hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
source=PARENT/'data/test.json'
original=json.loads(source.read_text())
suffix=" End with 'Answer: <number>'."
probe_questions=[
 'How many days make up one week?',
 'A complete year contains how many months?',
 'What is the number of sides in a triangle?',
 'An hour is equal to how many minutes?',
 'Express one meter as a number of centimeters.',
 'Find the sum of 17 and 26.',
 'Subtract 38 from 91. What is the result?',
 'Calculate the product of 7 and 8.',
 'Divide 81 into 9 equal parts. What is the size of each part?',
 'What is the number of sides in a hexagon?',
 'One day contains how many hours?',
 'Calculate one quarter of 80.'
]
rows=[]
for row in original:
    bits=row['id'].split('-');task=row['task']
    if task=='inventory':
        _,boxes,each,used=bits
        q=f'A storage room contains {boxes} cartons of pencils, with {each} pencils per carton. After {used} pencils are removed from this stock, how many pencils are left?'
    elif task=='discount':
        _,goods,shipping,threshold=bits
        q=f'The item subtotal on an order is {goods} dollars, and delivery costs {shipping} dollars. A store takes 20 dollars off only if the item subtotal meets or exceeds {threshold} dollars; delivery charges are excluded from this check. What is the discount amount in dollars?'
    elif task=='percentage':
        _,initial,pct=bits
        q=f'First a quantity of {initial} is raised by {pct} percent. It is then lowered by {pct} percent, with the reduction calculated from the raised quantity. Give the quantity after both changes.'
    else:q=probe_questions[int(bits[1])]
    rows.append(dict(id=row['id'],task=task,question=q+suffix,answer=row['answer']))
assert len(rows)==48 and len({r['question'] for r in rows})==48
assert all(a['question']!=b['question'] and a['answer']==b['answer'] for a,b in zip(original,rows))
write(ROOT/'reworded.json',rows)
artifacts={}
for tag in ['explained-seed17','answer_only-seed17','explained-seed29','answer_only-seed29']:
    for name in ['adapter_config.json','adapter_model.safetensors']:
        p=PARENT/'results'/f'{tag}-adapter'/name
        artifacts[str(p.relative_to(PARENT))]=digest(p)
protocol={
 'version':'sft-reworded-v1','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
 'purpose':'Post-hoc follow-up: separate final numerical correctness from Answer-field parsing; test one rewording per original item.',
 'source_commit':'09f085bda8c8877c7cec574e633434f879f5eccd',
 'base_model':'Qwen/Qwen2.5-0.5B-Instruct','base_revision':'7ae557604adf67be50417f59c2c2f167def9a775',
 'training':'No additional training. Reuse all four saved final-epoch adapters.',
 'evaluation':{'max_new_tokens':512,'do_sample':False,'num_beams':1,'batch_size':4,'threads':4,'system':'You are a helpful assistant.','dtype':'float32 parameters; CPU bfloat16 autocast'},
 'reuse':'Original baseline uses the existing baseline-512-posthoc.json; all other cells are newly generated. Four adapters are evaluated on both original and reworded inputs with the same 512-token budget.',
 'inputs':{'../data/test.json':digest(source),'reworded.json':digest(ROOT/'reworded.json'),'../results/baseline-512-posthoc.json':digest(PARENT/'results/baseline-512-posthoc.json')},
 'adapter_sha256':artifacts,
 'scoring':{
  'strict_legacy':'Preserve original parser and correct flag unchanged for comparison.',
  'format':'Report unambiguous explicit Answer-field parsing separately; this is not a full instruction-following metric.',
  'final_value':'Read the final claimed numerical answer, accepting an Answer field, final boxed number, or explicit closing numerical conclusion. Do not search for the reference value anywhere in the response.',
  'review':'Outputs not unambiguously resolved by extraction require a saved per-item review with an exact supporting quote. Reviews are not blind to model identity or prior results and do not constitute independent annotation.',
  'incomplete':'Generation at the 512-token cap is marked incomplete in the final-value metric.',
  'scope':'Judge final number only, not every intermediate step, explanation quality, spoken style, or general capabilities.'},
 'limits':['One English rewording per item; no new numbers or task types.','Test items are paired; seeds and rewordings are not independent new samples.','Original experiment and results were already known when this follow-up was designed.','Supervised token budgets remain unequal; this does not isolate an explanation mechanism.']
}
write(ROOT/'protocol.json',protocol)
print(json.dumps({'n':len(rows),'input_sha256':protocol['inputs'],'adapters':len(artifacts)//2}))
