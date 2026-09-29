"""Post-hoc baseline-only diagnostic after discovering 128-token truncation.

Does not retrain, replace primary results, or provide a new arm comparison.
"""
import argparse,json,socket,time
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from experiment import ROOT,SYSTEM,dump,score

p=argparse.ArgumentParser();p.add_argument('--model-dir',required=True);args=p.parse_args()
assert (ROOT/'results/complete.json').exists(), 'Run the fixed main experiment first'
torch.set_num_threads(4);torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True);torch.manual_seed(0)
tok=AutoTokenizer.from_pretrained(args.model_dir,local_files_only=True,trust_remote_code=False,padding_side='left')
tok.pad_token=tok.eos_token
model=AutoModelForCausalLM.from_pretrained(args.model_dir,local_files_only=True,trust_remote_code=False,
    torch_dtype=torch.float32,attn_implementation='eager')
model.eval()
def no_network(*a,**k):raise RuntimeError('Network disabled during experiment')
socket.socket.connect=no_network
rows=json.loads((ROOT/'data/test.json').read_text());records=[];t0=time.time()
for start in range(0,len(rows),4):
    batch=rows[start:start+4]
    prompts=[tok.apply_chat_template([dict(role='system',content=SYSTEM),dict(role='user',content=r['question'])],tokenize=False,add_generation_prompt=True) for r in batch]
    inputs=tok(prompts,return_tensors='pt',padding=True)
    with torch.inference_mode(),torch.autocast('cpu',dtype=torch.bfloat16):
        out=model.generate(**inputs,max_new_tokens=512,do_sample=False,num_beams=1,
            pad_token_id=tok.pad_token_id,eos_token_id=tok.eos_token_id)
    for row,tokens in zip(batch,out[:,inputs.input_ids.shape[1]:]):
        ids=tokens.tolist();n=ids.index(tok.eos_token_id)+1 if tok.eos_token_id in ids else len(ids)
        text=tok.decode(ids,skip_special_tokens=True);value=score(text)
        records.append(dict(id=row['id'],task=row['task'],question=row['question'],expected=row['answer'],
            output=text,parsed=value,correct=value==row['answer'],generated_tokens=n,
            hit_limit=tok.eos_token_id not in ids and len(ids)==512))
    print(json.dumps(dict(stage='posthoc_baseline_512',done=min(start+4,len(rows)),n=len(rows))),flush=True)
dump(ROOT/'results/baseline-512-posthoc.json',dict(tag='baseline-512-posthoc',max_new_tokens=512,
    purpose='Post-hoc baseline-only truncation diagnostic. Primary 128-token results remain unchanged.',
    seconds=time.time()-t0,records=records))
