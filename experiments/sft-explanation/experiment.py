"""Small, paired SFT pilot. Public synthetic data; no API calls during training."""
from __future__ import annotations
import argparse, collections, gc, hashlib, itertools, json, os, random, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_ID = 'Qwen/Qwen2.5-0.5B-Instruct'
REVISION = '7ae557604adf67be50417f59c2c2f167def9a775'
SYSTEM = 'You are a helpful assistant.'
SUFFIX = " End with 'Answer: <number>'."

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def build_data():
    pools = collections.defaultdict(list)
    for packs, size, used in itertools.product(range(3, 13), range(4, 14), range(1, 10)):
        answer = packs*size-used
        pools['inventory'].append(dict(id=f'inventory-{packs}-{size}-{used}', task='inventory',
            question=f'There are {packs} boxes with {size} pencils in each. {used} pencils are given away. How many pencils remain?'+SUFFIX,
            answer=answer, explanation=f'There are {packs} * {size} = {packs*size} pencils initially. After giving away {used}, {packs*size} - {used} = {answer} remain.'))
    for goods, shipping, threshold in itertools.product(range(150, 231, 10), range(10, 41, 5), (180, 200, 220)):
        answer = 20 if goods>=threshold else 0
        pools['discount'].append(dict(id=f'discount-{goods}-{shipping}-{threshold}',task='discount',
            question=f'A shop gives a 20-dollar discount when the item subtotal is at least {threshold} dollars. Shipping does not count toward the threshold. The items cost {goods} dollars and shipping is {shipping} dollars. How many dollars is the discount?'+SUFFIX,
            answer=answer, explanation=f'Only the item subtotal of {goods} counts; the {shipping}-dollar shipping charge is excluded. {goods} is '+('at least' if answer else 'below')+f' {threshold}, so the discount is {answer} dollars.'))
    for initial, percent in itertools.product(range(100, 1100, 100), (10, 20, 30, 40, 50)):
        raised = initial*(100+percent)//100
        answer = raised*(100-percent)//100
        pools['percentage'].append(dict(id=f'percentage-{initial}-{percent}',task='percentage',
            question=f'A value starts at {initial}, increases by {percent} percent, and then decreases by {percent} percent of its new value. What is the final value?'+SUFFIX,
            answer=answer, explanation=f'The increase gives {raised}. The decrease is {percent} percent of {raised}, which is {raised-answer}. The final value is {raised} - {raised-answer} = {answer}.'))
    train, test = [], []
    for task, rows in sorted(pools.items()):
        rows.sort(key=lambda r:hashlib.sha256(('nate-sft-pilot-v1:'+r['id']).encode()).hexdigest())
        train.extend(rows[:32]); test.extend(rows[32:44])
    for row in train:
        row['explained'] = row['explanation']+f" Answer: {row['answer']}."
        row['answer_only'] = f"Answer: {row['answer']}."
    # Small out-of-training-task probes, not a general capability benchmark.
    probes = [
      ('How many days are there in a week?',7),('How many months are there in a year?',12),
      ('How many sides does a triangle have?',3),('How many minutes are there in an hour?',60),
      ('How many centimeters are there in a meter?',100),('What is 17 plus 26?',43),
      ('What is 91 minus 38?',53),('What is 7 times 8?',56),('What is 81 divided by 9?',9),
      ('How many sides does a hexagon have?',6),('How many hours are there in a day?',24),
      ('What is 25 percent of 80?',20)]
    for i,(q,a) in enumerate(probes):
        test.append(dict(id=f'probe-{i:02}',task='probe',question=q+SUFFIX,answer=a))
    assert len(train)==96 and len(test)==48
    assert not ({r['question'] for r in train}&{r['question'] for r in test})
    for row in train+test:
        if row['task']=='percentage':
            _,n,p=row['id'].split('-')
            assert row['answer']==int(n)*(10000-int(p)**2)//10000
    return train,test

def prepare():
    train,test=build_data()
    dump(ROOT/'data/train.json',train); dump(ROOT/'data/test.json',test)
    protocol=dict(version='nate-sft-pilot-v1',model=MODEL_ID,revision=REVISION,
        objective='Exploratory paired comparison of explained versus answer-only correct targets.',
        train_n=96,test_in_distribution_n=36,probe_n=12,training_seeds=[17,29],
        epochs=3,batch_size=4,learning_rate=0.0002,optimizer='AdamW',weight_decay=0.0,
        lora=dict(r=8,alpha=16,dropout=0.0,modules=['q_proj','v_proj']),
        loss='Mean cross entropy over non-masked assistant tokens per batch; prompt/padding masked.',
        dtype='float32 parameters, CPU bfloat16 autocast',max_train_tokens=256,
        generation=dict(do_sample=False,num_beams=1,max_new_tokens=128,batch_size=4),
        threads=4,selection='Final epoch only; no evaluation-based checkpoint selection.',
        scoring='Last Answer: number match, at most one distinct answer value; absent/conflicting values are unparsed. No fallback extraction.',
        confounds=['Same sample/step budget, unequal supervised-token budget.','Synthetic English tasks, same templates in train and held-out-number test.','Only two seeds and one small text model.','12 probe items do not establish general capability retention.','Explanations repeat task-relevant information/numbers, not just style.'],
        data_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('*.json')})
    dump(ROOT/'protocol.json',protocol)
    return protocol

def encode(tok,row,arm):
    messages=[dict(role='system',content=SYSTEM),dict(role='user',content=row['question'])]
    prefix=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
    full=tok.apply_chat_template(messages+[dict(role='assistant',content=row[arm])],tokenize=True)
    assert full[:len(prefix)]==prefix, 'Chat-template prefix mismatch'
    assert len(full)<=256, 'Truncation would change this experiment'
    labels=[-100]*len(prefix)+full[len(prefix):]
    assert any(x!=-100 for x in labels) and tok.eos_token_id in labels
    return full,labels

def score(text):
    values=re.findall(r'(?i)\banswer\s*:\s*\$?\s*(-?\d+(?:\.\d+)?)',text)
    unique=set(float(v) for v in values)
    return next(iter(unique)) if len(unique)==1 else None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--model-dir');ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    if args.prepare_only:
        print(prepare());return
    # Data/protocol are frozen before any baseline outputs are viewed.
    protocol=json.loads((ROOT/'protocol.json').read_text())
    train=json.loads((ROOT/'data/train.json').read_text());test=json.loads((ROOT/'data/test.json').read_text())
    for name,digest in protocol['data_sha256'].items():
        assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest
    import torch,transformers,peft
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import LoraConfig,get_peft_model
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(0)
    tok=AutoTokenizer.from_pretrained(args.model_dir,local_files_only=True,trust_remote_code=False,padding_side='left')
    tok.pad_token=tok.eos_token
    base=AutoModelForCausalLM.from_pretrained(args.model_dir,local_files_only=True,trust_remote_code=False,torch_dtype=torch.float32,attn_implementation='eager')
    # Model and tokenizer now loaded; prohibit inference/training network access.
    import socket
    def no_network(*a,**k):raise RuntimeError('Network disabled during experiment')
    socket.socket.connect=no_network
    results=ROOT/('smoke' if args.smoke else 'results');results.mkdir(exist_ok=True)
    dump(results/'environment.json',dict(torch=torch.__version__,transformers=transformers.__version__,peft=peft.__version__,threads=torch.get_num_threads(),parameters=sum(p.numel() for p in base.parameters()),started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    prompts=lambda rows:[tok.apply_chat_template([dict(role='system',content=SYSTEM),dict(role='user',content=r['question'])],tokenize=False,add_generation_prompt=True) for r in rows]
    def evaluate(model,tag,rows):
        model.eval();records=[];t0=time.time()
        for start in range(0,len(rows),4):
            batch=rows[start:start+4];inputs=tok(prompts(batch),return_tensors='pt',padding=True)
            with torch.inference_mode(),torch.autocast('cpu',dtype=torch.bfloat16):
                out=model.generate(**inputs,max_new_tokens=128,do_sample=False,num_beams=1,pad_token_id=tok.pad_token_id,eos_token_id=tok.eos_token_id)
            for row,tokens in zip(batch,out[:,inputs.input_ids.shape[1]:]):
                ids=tokens.tolist();n=ids.index(tok.eos_token_id)+1 if tok.eos_token_id in ids else len(ids)
                text=tok.decode(ids,skip_special_tokens=True);value=score(text)
                rec=dict(id=row['id'],task=row['task'],question=row['question'],expected=row['answer'],output=text,parsed=value,correct=value==row['answer'],generated_tokens=n,hit_limit=tok.eos_token_id not in ids and len(ids)==128)
                records.append(rec)
            print(json.dumps(dict(stage='eval',tag=tag,done=min(start+4,len(rows)),n=len(rows))),flush=True)
        dump(results/f'{tag}.json',dict(tag=tag,seconds=time.time()-t0,records=records));return records
    baseline=evaluate(base,'baseline',test[:4] if args.smoke else test)
    arms=['explained'] if args.smoke else ['explained','answer_only']
    for seed in ([17] if args.smoke else protocol['training_seeds']):
      for arm in arms:
        tag=f'{arm}-seed{seed}';torch.manual_seed(seed)
        config=LoraConfig(r=8,lora_alpha=16,lora_dropout=0.0,target_modules=['q_proj','v_proj'],task_type='CAUSAL_LM',bias='none')
        model=get_peft_model(base,config);model.train();model.config.use_cache=False
        encoded=[encode(tok,r,arm) for r in train]
        parameters=[p for p in model.parameters() if p.requires_grad]
        before=[p.detach().clone() for p in parameters]
        opt=torch.optim.AdamW(parameters,lr=0.0002,weight_decay=0.0)
        losses=[];t0=time.time();supervised=0
        for epoch in range(1 if args.smoke else 3):
          order=list(range(len(train)));random.Random(seed+epoch*1000).shuffle(order)
          for start in range(0,4 if args.smoke else len(order),4):
            items=[encoded[i] for i in order[start:start+4]];width=max(len(a) for a,b in items)
            ids=torch.tensor([a+[tok.pad_token_id]*(width-len(a)) for a,b in items])
            masks=torch.tensor([[1]*len(a)+[0]*(width-len(a)) for a,b in items])
            labels=torch.tensor([b+[-100]*(width-len(b)) for a,b in items])
            opt.zero_grad(set_to_none=True)
            with torch.autocast('cpu',dtype=torch.bfloat16):
                loss=model(input_ids=ids,attention_mask=masks,labels=labels,use_cache=False).loss
            assert torch.isfinite(loss), 'Nonfinite loss'
            loss.backward();grad=torch.nn.utils.clip_grad_norm_(parameters,1.0);opt.step()
            count=int((labels[:,1:]!=-100).sum());supervised+=count
            losses.append(dict(step=len(losses)+1,epoch=epoch,loss=float(loss),supervised_tokens=count,grad_norm=float(grad)))
            if len(losses)%6==0 or args.smoke:print(json.dumps(dict(stage='train',tag=tag,step=len(losses),loss=float(loss),seconds=time.time()-t0)),flush=True)
        change=sum(float((a.detach()-b).abs().sum()) for a,b in zip(parameters,before))
        assert change>0,'Adapter did not change'
        dump(results/f'{tag}-training.json',dict(trainable_parameters=sum(p.numel() for p in parameters),steps=len(losses),supervised_tokens=supervised,adapter_l1_change=change,seconds=time.time()-t0,losses=losses))
        model.save_pretrained(results/f'{tag}-adapter')
        model.config.use_cache=True
        evaluate(model,tag,test[:4] if args.smoke else test)
        # Remove adapter WITHOUT merging: each arm starts from the same frozen base.
        base=model.unload();del opt,model,parameters,before;gc.collect()
    dump(results/'complete.json',dict(completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),smoke=args.smoke))

if __name__=='__main__':main()
