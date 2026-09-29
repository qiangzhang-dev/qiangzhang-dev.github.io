"""Build the complete paired report from scored records and raw responses."""
import collections,html,json
from pathlib import Path
from score import TAGS
ROOT=Path(__file__).resolve().parent
assert (ROOT/'results/complete.json').exists(),'Inference incomplete'
scored=json.loads((ROOT/'scored.json').read_text())
assert scored['pending_count']==0 and len(scored['records'])==480
records=scored['records'];names={'baseline':'原始指令模型','explained-seed17':'保留解释 · 17','answer_only-seed17':'只留结论 · 17','explained-seed29':'保留解释 · 29','answer_only-seed29':'只留结论 · 29'}
variants={'original':'原题','reworded':'改写题'};E=html.escape
cells={};raw={};pairs=[]
for tag in TAGS:
 for variant in variants:
  key=f'{tag}/{variant}';rows=[x for x in records if x['tag']==tag and x['variant']==variant]
  raw[key]=json.loads((ROOT/'results'/f'{tag}-{variant}.json').read_text())
  cells[key]={}
  for group in ['within_template','probe']:
   a=[x for x in rows if (x['task']=='probe')==(group=='probe')]
   cells[key][group]=dict(n=len(a),value_correct=sum(x['value_correct'] for x in a),terminal_format=sum(x['terminal_answer_format'] for x in a),
    legacy_correct=sum(x['legacy_correct'] for x in a),unresolved=sum(x['final_value'] is None for x in a),hit_limit=sum(x['hit_limit'] for x in a))
  cells[key]['tasks']={t:dict(correct=sum(x['value_correct'] for x in rows if x['task']==t),n=sum(x['task']==t for x in rows),
    values=dict(collections.Counter(str(x['final_value']) for x in rows if x['task']==t))) for t in ['discount','inventory','percentage','probe']}
 a={x['id']:x for x in records if x['tag']==tag and x['variant']=='original' and x['task']!='probe'}
 b={x['id']:x for x in records if x['tag']==tag and x['variant']=='reworded' and x['task']!='probe'}
 pairs.append(dict(tag=tag,improved=[id for id in a if not a[id]['value_correct'] and b[id]['value_correct']],regressed=[id for id in a if a[id]['value_correct'] and not b[id]['value_correct']]))
summary=dict(cells=cells,paired_changes=pairs,manual_review_count=sum(x['decision']['method']=='documented_review' for x in records))
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
rows='';probe_rows='';task_rows=''
for tag in TAGS:
 a,b=[cells[f'{tag}/{v}']['within_template'] for v in variants]
 p,q=[cells[f'{tag}/{v}']['probe'] for v in variants]
 rows+=f'<tr><th scope="row">{names[tag]}</th><td>{a["value_correct"]}/36</td><td>{b["value_correct"]}/36</td><td>{a["terminal_format"]}/36</td><td>{b["terminal_format"]}/36</td></tr>'
 probe_rows+=f'<tr><th scope="row">{names[tag]}</th><td>{p["value_correct"]}/12 → {q["value_correct"]}/12</td><td>{p["terminal_format"]}/12 → {q["terminal_format"]}/12</td><td>{a["unresolved"]+p["unresolved"]} → {b["unresolved"]+q["unresolved"]}</td><td>{a["hit_limit"]+p["hit_limit"]} → {b["hit_limit"]+q["hit_limit"]}</td></tr>'
 task_rows+=f'<tr><th scope="row">{names[tag]}</th>'+''.join(f'<td>{cells[f"{tag}/original"]["tasks"][t]["correct"]} → {cells[f"{tag}/reworded"]["tasks"][t]["correct"]}</td>' for t in ['discount','inventory','percentage'])+'</tr>'
change_rows=''.join(f'<tr><th scope="row">{names[p["tag"]]}</th><td>{len(p["improved"])}</td><td>{len(p["regressed"])}</td><td>{36-len(p["improved"])-len(p["regressed"])}</td></tr>' for p in pairs)
baseline=[x for x in records if x['tag']=='baseline' and x['variant']=='original' and x['task']!='probe']
contingency=[sum(x['terminal_answer_format']==f and x['value_correct']==c for x in baseline) for f,c in [(True,True),(True,False),(False,True),(False,False)]]
lookup={x['key']:x for x in records}
rawlookup={f'{tag}/{variant}/{x["id"]}':x for tag in TAGS for variant in variants for x in raw[f'{tag}/{variant}']['records']}
examples=''
ids=[x['id'] for x in raw['baseline/original']['records']]
for id in ids:
 item=rawlookup[f'baseline/original/{id}'];task=item['task']
 changed=any(lookup[f'{tag}/original/{id}']['value_correct']!=lookup[f'{tag}/reworded/{id}']['value_correct'] for tag in TAGS)
 examples+=f'<details class="sample" id="case-{id}" data-task="{task}" data-changed="{str(changed).lower()}"><summary>{id} <span>· 正确值 {item["expected"]}</span></summary><p><strong>原题：</strong>{E(item["question"])}</p><p><strong>改写题：</strong>{E(rawlookup[f"baseline/reworded/{id}"]["question"])}</p>'
 for tag in TAGS:
  examples+=f'<h3>{names[tag]}</h3><div class="pair">'
  for variant in variants:
   key=f'{tag}/{variant}/{id}';record=lookup[key];x=rawlookup[key]
   status='最终数值正确' if record['value_correct'] else ('未给出可确定的最终数值' if record['final_value'] is None else '最终数值不正确')
   fmt='可提取末尾 Answer 字段' if record['terminal_answer_format'] else '未通过末尾 Answer 格式检查'
   examples+=f'<section><h4>{variants[variant]} · {status}</h4><p class="meta">{fmt} · {x["generated_tokens"]} tokens</p><pre>{E(x["output"])}</pre><details class="decision"><summary>判分依据</summary><p>{E(record["decision"]["method"])} · 提取值 {record["final_value"]}</p><blockquote>{E(record["decision"]["quote"])}</blockquote></details></section>'
  examples+='</div>'
 examples+='</details>'
# One deterministic changed case, selected by fixed model/item order.
changed_case=''
for p in pairs[1:]:
 if p['regressed']:
  id=p['regressed'][0];tag=p['tag'];a=rawlookup[f'{tag}/original/{id}'];b=rawlookup[f'{tag}/reworded/{id}']
  changed_case=f'<h3>一个改写后答错的例子</h3><p>按固定模型和题目顺序，第一道从正确变为未通过的微调模型样本是 <a href="#case-{id}">{id}</a>（{names[tag]}）。正确数值为 {a["expected"]}。</p><p class="meta">原题输出</p><blockquote>{E(a["output"])}</blockquote><p class="meta">改写题输出</p><blockquote>{E(b["output"])}</blockquote>'
  break
matches=[raw[f'{t}/original']['versus_prior_128']['exact_output_matches'] for t in TAGS[1:]]
matchtext='四个微调版本的原题重测均与之前逐字一致（每个版本 48/48）。' if matches==[48]*4 else f'四个微调版本与此前 128-token 原题输出的逐字一致条数依次为 {matches}，完整差异 ID 保留在原始 JSON 中。'
body=f'''<nav aria-label="页面导航"><a href="/">Nate / 个人网站</a><a href="../results/">第一次 SFT 对照</a><a href="https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/experiments/sft-explanation/followup">代码与记录 ↗</a><a href="https://zhuanlan.zhihu.com/p/2088312597007409375">知乎文章 ↗</a></nav><article><h1>换个问法，<br>再把格式与答案分开评测</h1><p class="meta">2026-09-29 · Qiang (Nate) Zhang · SFT 对照后续 / 未追加训练</p><p class="lead">没有追加训练，只改写题干：保留解释组从 32/36、35/36 都降到 17/36，只留结论组从 16/36、17/36 降到 10/36、5/36。原模型则从 17/36 升到 24/36。第一轮固定模板上的高分，没有完整保留到这套改写题上。</p><h2>2/36 和 17/36，分别数了什么</h2><p>这两个数字都来自原模型在 <strong>512-token 上限下的同一批原题输出</strong>。旧评分要求读到正确的 Answer 数值；新评分允许答案写在公式框或最后一句话里，只判断最后主张的数值是否正确。</p><p>例如 <a href="#case-inventory-8-11-2">inventory-8-11-2</a>，模型算出了 8 × 11 − 2 = 86，并把 86 放进公式框。按旧规则没有通过，按最终数值计则正确。两种指标描述的是不同问题。</p><div class="table-wrap"><table><caption>原模型 / 原题，36 道任务题</caption><thead><tr><th>末尾 Answer 格式</th><th>最终数值正确</th><th>最终数值未通过</th></tr></thead><tbody><tr><th scope="row">通过</th><td>{contingency[0]}</td><td>{contingency[1]}</td></tr><tr><th scope="row">未通过</th><td>{contingency[2]}</td><td>{contingency[3]}</td></tr></tbody></table></div><p>“格式通过”只表示机器能读到一个明确的末尾 Answer 字段，不要求这个数字正确；“数值正确”也不要求一定使用 Answer 字段。这次还收紧了字段的结尾检查，并兼容加粗和常见单位，具体规则保留在<a href="score.py">判分脚本</a>里。</p><p>还发现一个旧解析器的问题：<code>Answer: 230 - 46 = 184</code> 会被读成 230。本轮留下原句和复核记录，把最终主张记为 184，同时判定它未满足末尾 Answer 数值格式。这道题本来应该答 20，因此两个数字都不正确，但错误类型不能混淆。</p><h2>不改模型，只改题干</h2><p>复用第一次实验的四个 LoRA 适配器，不再训练。原题和改写题使用同样的 greedy 解码、512-token 上限、系统提示和每批 4 题的设置。原模型的原题记录复用之前的 512-token 诊断，其余九个评测单元重新生成，共 432 条回答。</p><p>保留题目中的数学条件和正确答案，每题只做一种英文改写。例如把 boxes 换成 cartons、调整满减规则的叙述顺序；额外探针中也把 25 percent 改成 one quarter。结尾的 Answer 指令保持一致。它检验的是这些具体改写，不是任意问法，也不是新题型泛化。</p><p>{matchtext}改写题、协议和适配器校验值见<a href="protocol.json">固定输入记录</a>。这轮是在看过第一次结果后设计的后续检查。</p><h2>36 道任务题：数值和格式分别报告</h2><div class="table-wrap"><table><thead><tr><th>模型 / 种子</th><th>原题数值正确</th><th>改写题数值正确</th><th>原题格式通过</th><th>改写题格式通过</th></tr></thead><tbody>{rows}</tbody></table></div><div class="table-wrap"><table><caption>最终数值正确数，原题 → 改写题；每类 12 道</caption><thead><tr><th>模型 / 种子</th><th>满减条件</th><th>数量计算</th><th>百分比</th></tr></thead><tbody>{task_rows}</tbody></table></div><p>两种训练目标仍然使用不同的监督 token 预算：保留解释组 13,974，只留结论组 2,349。这里不能把任何差异单独归因于“解释”这一因素。</p><p><strong>在这套具体改写上，四个微调版本的最终数值正确数都低于原模型。</strong>保留解释组仍高于只留结论组，但首轮原题上的优势不能直接当作已经获得了稳定的解题能力。这里说的是这一批题、这些改写和这些检查点，原因仍需另做对照。</p><h2>同一题，哪些从对变错了</h2><div class="table-wrap"><table><caption>36 道配对任务题，按最终数值判断</caption><thead><tr><th>模型 / 种子</th><th>原题未通过 → 改写题正确</th><th>原题正确 → 改写题未通过</th><th>判定未变</th></tr></thead><tbody>{change_rows}</tbody></table></div>{changed_case}<h2>额外探针与未能判定的回答</h2><div class="table-wrap"><table><caption>均为原题 → 改写题；12 道探针不能代表通用能力</caption><thead><tr><th>模型 / 种子</th><th>探针数值正确</th><th>探针格式通过</th><th>最终数值未确定 / 48</th><th>达到长度上限 / 48</th></tr></thead><tbody>{probe_rows}</tbody></table></div><p>最终数值未确定的情况单独计数。例如只返回 <code>0.99Q</code>，没有代入题目给定的初值，本轮不会替模型完成代入，再把它当作已输出了正确数字。这不等于说这个符号公式本身一定错了。</p><h2>这轮最值得改进的，是怎么读分数</h2><p>先明确通过条件，再解释训练结果。格式、最终数字、推导过程和表达质量是不同的观察对象。这次只分别检查了前两项；最终数字正确，也可能伴随错误的中间步骤。</p><p>题干变化也需要配对看。同一个模型在部分题上改善、另一些题上变差，净分数只能显示其中一部分。一次英文改写、36 道任务题、两个种子都不足以证明稳健性，数据和训练预算上的限制也没有因为多跑一次评测而消失。</p><p>评分中的自动提取不读取参考答案；无法明确提取的记录逐条留下原句和处理理由。这些复核可见模型身份和旧结果，没有独立标注者复核。第一次实验的原始记录和评分没有被覆盖。</p><h2>复现与逐题证据</h2><ul><li><a href="README.md">运行说明</a> · <a href="run.py">推理脚本</a> · <a href="score.py">判分脚本</a> · <a href="report.py">本页生成脚本</a></li><li><a href="reworded.json">48 道改写题</a> · <a href="../data/test.json">原题</a> · <a href="protocol.json">协议与校验值</a></li><li><a href="summary.json">汇总结果</a> · <a href="scored.json">480 条判分记录</a> · <a href="reviews.json">需单独复核的记录</a> · <a href="https://github.com/qiangzhang-dev/qiangzhang-dev.github.io/tree/main/experiments/sft-explanation/followup/results">全部原始输出 ↗</a></li></ul><h2 id="all-cases">原题与改写题并排看</h2><div class="controls"><label>题型 <select id="task"><option value="all">全部</option><option value="discount">满减条件</option><option value="inventory">数量计算</option><option value="percentage">百分比</option><option value="probe">额外探针</option></select></label><label><input type="checkbox" id="changed"> 只看至少一个模型判定变化的题</label><output id="count" aria-live="polite">48 / 48 道</output></div><div id="samples">{examples}</div></article><footer>Qiang (Nate) Zhang · <a href="../results/">第一次实验</a> · <a href="/">个人网站</a></footer>'''
style='''*{box-sizing:border-box}body{margin:0;background:#fff;color:#30343b;font:16px/1.85 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1100px;padding:40px 28px 70px;margin:auto}nav{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:36px;font-size:14px}a{color:#1766aa;text-underline-offset:4px}h1{font-size:clamp(28px,4.5vw,36px);line-height:1.45;letter-spacing:-.025em;color:#181b20;margin-bottom:12px}h2{font-size:23px;line-height:1.5;margin:38px 0 14px}h3{font-size:17px}h4{font-size:15px}.meta,caption{color:#69717c;font-size:14px}.lead{font-size:18px}.table-wrap{overflow:auto;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;border-bottom:1px solid #dde3e9;text-align:left;white-space:nowrap}thead th{background:#f5f7fa}tbody th{font-weight:500}caption{text-align:left;margin-bottom:9px}p{margin:16px 0}blockquote{margin:12px 0;padding:14px 18px;border-left:3px solid #d9b582;background:#fafafa;overflow-wrap:anywhere}code{font-size:.88em;background:#f3f5f7;padding:2px 4px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:16px;font:13px/1.75 ui-monospace,monospace}.sample{border-bottom:1px solid #dde3e9;padding:15px 0}.sample>summary{font-weight:600;padding:4px 0}.sample>summary span{font-weight:400;color:#69717c}summary{cursor:pointer}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}.pair section{min-width:0}.decision{font-size:13px}.controls{display:flex;gap:15px;flex-wrap:wrap;align-items:center;padding:16px;background:#f5f7fa;font-size:14px}select{font:inherit;padding:6px;background:white;border:1px solid #ccd3dd;border-radius:3px}li{margin:10px 0}footer{margin-top:40px;border-top:1px solid #dde3e9;padding-top:20px;font-size:13px;color:#69717c}a:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #1766aa;outline-offset:4px}[hidden]{display:none!important}@media(max-width:700px){main{padding:24px 18px 50px}.pair{grid-template-columns:1fr}th,td{padding:10px}h2{font-size:21px}.lead{font-size:17px}}'''
script="""const task=document.querySelector('#task'),changed=document.querySelector('#changed');function filter(){let n=0;document.querySelectorAll('.sample').forEach(el=>{el.hidden=!((task.value==='all'||el.dataset.task===task.value)&&(!changed.checked||el.dataset.changed==='true'));if(!el.hidden)n++});document.querySelector('#count').textContent=n+' / 48 道'}task.addEventListener('change',filter);changed.addEventListener('change',filter);"""
doc=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>换个问法，再把格式与答案分开评测 · Nate Zhang</title><meta name="description" content="复用四个 SFT 适配器，不追加训练：用同样的生成预算比较原题与改写题，分别核对格式和最终数值。"><link rel="canonical" href="https://qiangzhang-dev.github.io/experiments/sft-explanation/followup/"><style>{style}</style></head><body><main>{body}</main><script>{script}</script></body></html>'
(ROOT/'index.html').write_text(doc)
print(json.dumps({'cells':len(cells),'scored':len(records),'reviewed':summary['manual_review_count'],'page_bytes':len(doc.encode())}))
