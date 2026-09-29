"""Fetch only the pinned official model files; never execute repository code."""
import argparse, hashlib, json
from pathlib import Path
from huggingface_hub import snapshot_download
from experiment import MODEL_ID, REVISION

p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
root=Path(snapshot_download(MODEL_ID,revision=REVISION,local_dir=a.output,
    allow_patterns=['*.json','*.txt','model.safetensors','LICENSE','README.md']))
records={}
for path in sorted(root.iterdir()):
    if not path.is_file() or path.name.startswith('.'):continue
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
    records[path.name]={'bytes':path.stat().st_size,'sha256':digest.hexdigest()}
Path(__file__).with_name('model-manifest.json').write_text(json.dumps(
    {'model':MODEL_ID,'revision':REVISION,'files':records},indent=2)+'\n')
print(root)
