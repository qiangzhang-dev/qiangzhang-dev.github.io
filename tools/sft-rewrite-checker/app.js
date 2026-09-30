import { analyze, parseRecords, makeReport, DECISIONS, RULES, MAX_REPORT_BYTES, textLength } from './core.js';
import { EXAMPLES } from './examples.js';

const $ = id => document.getElementById(id);
const PAGE_SIZE = 25;
let records = [];
let page = 1;
let exportUrl = null;

function clearExport() {
  if (exportUrl) {
    URL.revokeObjectURL(exportUrl);
    exportUrl = null;
    message('审核记录已修改，请重新导出。');
  }
  $('export-panel').hidden = true;
  $('export-json').value = '';
  $('download-records').removeAttribute('href');
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function message(text, error = false) {
  $('message').textContent = text;
  $('message').classList.toggle('error', error);
}
function labeledText(title, text) {
  const box = element('div');
  box.append(element('span', title, 'label'), element('p', text, 'text'));
  return box;
}
function renderStats() {
  const flagged = records.filter(record => record.findings.length).length;
  const pending = records.filter(record => record.review.decision === 'pending').length;
  const counts = [[records.length, '样本'], [flagged, '有差异线索'], [pending, '待复核'], [records.length - pending, '已填写结论']];
  $('stats').replaceChildren(...counts.map(([count, label]) => {
    const node = element('div', undefined, 'stat');
    node.append(element('strong', String(count)), element('span', label));
    return node;
  }));
}

function renderCard(record, index) {
  const card = element('article', undefined, 'card');
  const header = element('div', undefined, 'card-header');
  const status = element('span', DECISIONS[record.review.decision], 'card-status');
  header.append(element('h3', record.id), status);
  const body = element('div', undefined, 'card-body');
  const input = labeledText('完整训练输入', record.input);
  input.className = 'input-context';
  const comparison = element('div', undefined, 'comparison');
  comparison.append(labeledText('原答案 · ' + textLength(record.original) + ' 非空白字符', record.original), labeledText('改写答案 · ' + textLength(record.rewrite) + ' 非空白字符', record.rewrite));
  body.append(input, comparison);
  if (record.findings.length) {
    const cues = element('div', undefined, 'cues');
    cues.append(...record.findings.map(finding => element('span', finding.title, 'cue')));
    const details = element('details', undefined, 'evidence');
    details.append(element('summary', '查看 ' + record.findings.length + ' 条提示的依据'));
    for (const finding of record.findings) {
      const item = element('div', undefined, 'finding');
      item.append(element('h4', finding.title), element('p', finding.detail));
      const pair = element('div', undefined, 'evidence-pair');
      pair.append(element('p', '原答案：' + finding.original), element('p', '改写：' + finding.rewrite));
      item.append(pair); details.append(item);
    }
    body.append(cues, details);
  } else body.append(element('p', '未命中这些规则。仍需检查事实、语义和任务要求。', 'no-cues'));
  const review = element('div', undefined, 'review-fields');
  const decisionBox = element('div');
  const decisionLabel = element('label', '审核结论');
  const decision = element('select');
  decision.id = 'decision-' + index;
  decisionLabel.htmlFor = decision.id;
  decision.setAttribute('aria-label', record.id + ' 审核结论');
  for (const [value, label] of Object.entries(DECISIONS)) {
    const option = element('option', label); option.value = value; decision.append(option);
  }
  decision.value = record.review.decision;
  decision.addEventListener('change', () => {
    record.review.decision = decision.value;
    clearExport();
    status.textContent = DECISIONS[decision.value];
    renderStats();
    if ($('decision').value !== 'all') renderResults();
  });
  decisionBox.append(decisionLabel, decision);
  const noteBox = element('div');
  const noteLabel = element('label', '审核备注');
  const note = element('textarea');
  note.id = 'note-' + index;
  noteLabel.htmlFor = note.id;
  note.setAttribute('aria-label', record.id + ' 审核备注');
  note.rows = 2; note.maxLength = 10000;
  note.placeholder = '记录具体改动、输入依据和处理理由';
  note.value = record.review.note;
  note.addEventListener('input', () => { record.review.note = note.value; clearExport(); });
  noteBox.append(noteLabel, note);
  review.append(decisionBox, noteBox); body.append(review);
  card.append(header, body);
  return card;
}

function renderResults() {
  const search = $('search').value.normalize('NFKC').toLowerCase().trim();
  const rule = $('rule').value;
  const decision = $('decision').value;
  const filtered = records.map((record, index) => ({ record, index })).filter(({ record }) => {
    if (search && ![record.id, record.input, record.original, record.rewrite].some(text => text.normalize('NFKC').toLowerCase().includes(search))) return false;
    if (rule === 'flagged' && !record.findings.length) return false;
    if (rule === 'none' && record.findings.length) return false;
    if (Object.hasOwn(RULES, rule) && !record.findings.some(finding => finding.code === rule)) return false;
    return decision === 'all' || record.review.decision === decision;
  });
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  page = Math.min(page, pages);
  const begin = (page - 1) * PAGE_SIZE;
  $('cards').replaceChildren(...filtered.slice(begin, begin + PAGE_SIZE).map(({ record, index }) => renderCard(record, index)));
  $('empty').hidden = filtered.length !== 0;
  $('result-count').textContent = '筛选后 ' + filtered.length + ' / ' + records.length + ' 条' + (filtered.length ? ' · 当前 ' + (begin + 1) + '–' + Math.min(begin + PAGE_SIZE, filtered.length) : '');
  $('page-count').textContent = page + ' / ' + pages;
  $('previous').disabled = page === 1;
  $('next').disabled = page === pages;
}

function runAnalysis() {
  try {
    const parsed = parseRecords($('data').value);
    clearExport();
    records = parsed.map(record => ({ ...record, findings: analyze(record) }));
    page = 1;
    $('search').value = ''; $('rule').value = 'all'; $('decision').value = 'all';
    $('review').hidden = false;
    renderStats(); renderResults();
    message('已检查 ' + records.length + ' 条。审核记录只在当前页面内保留，导出后可重新导入继续。');
  } catch (error) {
    message(error.message + (records.length ? ' 未替换现有审核记录。' : ''), true);
  }
}

for (const [value, label] of Object.entries(RULES)) {
  const option = element('option', label); option.value = value; $('rule').append(option);
}
$('analyze').addEventListener('click', runAnalysis);
$('examples').addEventListener('click', () => {
  $('data').value = EXAMPLES.map(record => JSON.stringify(record)).join('\n');
  $('file').value = '';
  runAnalysis();
});
$('file').addEventListener('change', async () => {
  const file = $('file').files[0];
  if (!file) return;
  if (file.size > MAX_REPORT_BYTES) { message('文件超过 64 MiB。普通数据最多 5 MiB，导出的审核记录最多 64 MiB。', true); return; }
  try {
    $('data').value = await file.text();
    message('已读取 ' + file.name + '。点击“检查差异”后载入这批数据。');
  } catch { message('无法读取文件，请重新选择或粘贴数据。', true); }
});
for (const id of ['search', 'rule', 'decision']) $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { page = 1; renderResults(); });
$('previous').addEventListener('click', () => { page--; renderResults(); $('review').scrollIntoView({ block: 'start' }); });
$('next').addEventListener('click', () => { page++; renderResults(); $('review').scrollIntoView({ block: 'start' }); });
$('export').addEventListener('click', () => {
  const report = makeReport(records);
  const json = JSON.stringify(report, null, 2) + '\n';
  if (exportUrl) URL.revokeObjectURL(exportUrl);
  exportUrl = URL.createObjectURL(new Blob([json], { type: 'application/json;charset=utf-8' }));
  $('download-records').href = exportUrl;
  $('download-records').download = 'sft-rewrite-review-' + new Date().toISOString().slice(0, 10) + '.json';
  $('export-json').value = json;
  $('export-panel').hidden = false;
  message('已生成全部 ' + records.length + ' 条审核记录（不受当前筛选限制）。可下载或展开复制 JSON，重新导入可以继续审核。');
});
$('select-json').addEventListener('click', () => { $('export-json').focus(); $('export-json').select(); });
