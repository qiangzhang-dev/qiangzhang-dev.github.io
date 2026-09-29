"""Evaluate saved adapters, without training, on paired original/reworded inputs."""
import argparse,gc,hashlib,json,socket,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent
sys.path.insert(0,str(PARENT))
from experiment import SYSTEM,dump,score
p=argparse.ArgumentParser();p.add_argument('--model-dir',required=True);args=p.parse_args()
protocol=json.loads((ROOT/'protocol.json').read_text())
for rel,sha in protocol['inputs'].items():
    assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==sha,rel
for rel,sha in protocol['adapter_sha256'].items():
    assert hashlib.sha256((PARENT/rel).read_bytes()).hexdigest()==sha,rel
manifest=json.loads((PARENT/'model-manifest.json').read_text())
assert hashlib.file_digest(open(Path(args.model_dir)/'model.safetensors','rb'),'sha256').hexdigest()==manifest['files']['model.safetensors']['sha256']
import torch,transformers,peft
from transformers import AutoModelForCausalLM,AutoTokenizer
from peft import PeftModel

torch.set_num_threads(4);torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True);torch.manual_seed(0)
tok=AutoTokenizer.from_pretrained(args.model_dir,local_files_only=True,trust_remote_code=False,padding_side='left');tok.pad_token=tok.eos_token
base=AutoModelForCausalLM.from_pretrained(args.model_dir,local_files_only=True,trust_remote_code=False,
    torch_dtype=torch.float32,attn_implementation='eager')
def no_network(*a,**k):raise RuntimeError('Network disabled during evaluation')
socket.socket.connect=no_network
outdir=ROOT/'results';outdir.mkdir(exist_ok=True)
dump(outdir/'environment.json',dict(torch=torch.__version__,transformers=transformers.__version__,peft=peft.__version__,threads=4,
    started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),protocol_sha256=hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest()))
original=json.loads((PARENT/'data/test.json').read_text());reworded=json.loads((ROOT/'reworded.json').read_text())
reused=json.loads((PARENT/'results/baseline-512-posthoc.json').read_text())
assert all((r['id'],r['question'],r['expected'])==(q['id'],q['question'],q['answer']) for r,q in zip(reused['records'],original))
reused['tag']='baseline';reused['variant']='original';reused['reused_from']='../../results/baseline-512-posthoc.json'
dump(outdir/'baseline-original.json',reused)

def evaluate(model,tag,variant,rows):
    model.eval();model.config.use_cache=True;records=[];t0=time.time()
    for start in range(0,len(rows),4):
        batch=rows[start:start+4]
        prompts=[tok.apply_chat_template([dict(role='system',content=SYSTEM),dict(role='user',content=r['question'])],tokenize=False,add_generation_prompt=True) for r in batch]
        inputs=tok(prompts,return_tensors='pt',padding=True)
        with torch.inference_mode(),torch.autocast('cpu',dtype=torch.bfloat16):
            out=model.generate(**inputs,max_new_tokens=512,do_sample=False,num_beams=1,pad_token_id=tok.pad_token_id,eos_token_id=tok.eos_token_id)
        for row,tokens in zip(batch,out[:,inputs.input_ids.shape[1]:]):
            ids=tokens.tolist();n=ids.index(tok.eos_token_id)+1 if tok.eos_token_id in ids else len(ids)
            text=tok.decode(ids,skip_special_tokens=True);value=score(text)
            records.append(dict(id=row['id'],task=row['task'],question=row['question'],expected=row['answer'],output=text,parsed=value,
                correct=value==row['answer'],generated_tokens=n,hit_limit=tok.eos_token_id not in ids and len(ids)==512))
        print(json.dumps(dict(tag=tag,variant=variant,done=min(start+4,len(rows)),n=len(rows))),flush=True)
    result=dict(tag=tag,variant=variant,max_new_tokens=512,seconds=time.time()-t0,records=records)
    if variant=='original':
        prior=json.loads((PARENT/'results'/f'{tag}.json').read_text())['records']
        result['versus_prior_128']={'exact_output_matches':sum(a['output']==b['output'] for a,b in zip(prior,records)),
            'changed_ids':[a['id'] for a,b in zip(prior,records) if a['output']!=b['output']]}
    dump(outdir/f'{tag}-{variant}.json',result)

evaluate(base,'baseline','reworded',reworded)
for tag in ['explained-seed17','answer_only-seed17','explained-seed29','answer_only-seed29']:
    model=PeftModel.from_pretrained(base,str(PARENT/'results'/f'{tag}-adapter'),is_trainable=False,local_files_only=True)
    assert not any(p.requires_grad for p in model.parameters()), 'Inference must not update parameters'
    for variant,rows in [('original',original),('reworded',reworded)]:evaluate(model,tag,variant,rows)
    base=model.unload();del model;gc.collect()
dump(outdir/'complete.json',dict(completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),new_generated_responses=432,reused_responses=48,training_steps=0))
