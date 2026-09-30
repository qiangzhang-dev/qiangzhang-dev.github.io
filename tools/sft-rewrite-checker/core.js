export const VERSION = '0.1.1';
export const SCHEMA = 'sft-rewrite-review/v1';
export const MAX_BYTES = 5 * 1024 * 1024;
export const MAX_REPORT_BYTES = 64 * 1024 * 1024;
export const MAX_RECORDS = 5000;
export const DECISIONS = { pending: '待复核', keep: '保留', revise: '返修', hold: '搁置' };
export const RULES = {
  numbers: '数字 / 单位变化',
  anchors: '指定短语未保留',
  conditions: '条件线索减少',
  certainty: '不确定性线索减少',
  clarification: '澄清请求线索减少',
  length: '答案大幅缩短',
  format: 'Markdown 标记变化',
};

const normalize = text => text.normalize('NFKC').replace(/\u2212/g, '-').toLowerCase();
const escapeRegex = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const clip = (text, max = 180) => Array.from(text).slice(0, max).join('') + (Array.from(text).length > max ? '…' : '');
export const textLength = text => Array.from(text.replace(/\s/g, '')).length;

function mention(text, term) {
  const haystack = normalize(text);
  const word = normalize(term);
  const regex = /[a-z]/i.test(word)
    ? new RegExp('\\b' + escapeRegex(word) + '\\b', 'g')
    : new RegExp(escapeRegex(word), 'g');
  for (const match of haystack.matchAll(regex)) {
    if (word === '可能' && haystack[match.index - 1] === '不') continue;
    return { term, excerpt: clip(haystack.slice(Math.max(0, match.index - 30), match.index + word.length + 70)) };
  }
  return null;
}

function signals(text, terms) {
  return terms.map(term => mention(text, term)).filter(Boolean);
}

const CONDITION_GROUPS = [
  ['成立条件', ['如果', '仅当', '只有', '只要', '除非', 'if', 'unless', 'only when', 'provided that']],
  ['排除项', ['不计入', '不算', '不包含', '不包括', '不含', '排除', '除外', 'except', 'excluding', 'excluded']],
  ['下限', ['至少', '不低于', '不少于', 'at least', 'no less than']],
  ['上限', ['至多', '最多', '不超过', 'at most', 'no more than']],
];
const UNCERTAINTY = ['可能', '或许', '不能确定', '不确定', '不一定', '通常', '一般情况下', 'may', 'might', 'could', 'usually', 'uncertain'];
const ASSERTION = ['肯定', '一定是', '就是', '必然', '总是', '保证', 'definitely', 'certainly', 'always', 'must be'];
const CLARIFICATION = ['你指的是', '请提供', '需要提供', '请补充', '能否提供', '哪个产品', '哪些产品', 'please provide', 'could you clarify', 'need more information', 'which product'];

export function numericTokens(text) {
  const tokens = [];
  const normalized = normalize(text);
  // Lexical comparison only: do not convert units or infer what a number means.
  const pattern = /(?<![a-z0-9_])[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:个百分点|百分比|百分数|千米|公里|毫米|厘米|分钟|小时|毫秒|公斤|千克|万元|亿元|元|米|秒|克|度|岁|倍|个|条|件|天|年|%|percent(?:age points)?\b|percentage points\b|km\b|cm\b|mm\b|ms\b|kg\b|gb\b|mb\b|kb\b|m\b|s\b|g\b)?/gu;
  for (const match of normalized.matchAll(pattern)) {
    tokens.push(match[0].replace(/\s+/g, '').replace(/,/g, '').replace(/^\+/, ''));
  }
  return tokens;
}

function difference(left, right) {
  const counts = new Map();
  for (const token of right) counts.set(token, (counts.get(token) || 0) + 1);
  return left.filter(token => {
    if (counts.get(token)) { counts.set(token, counts.get(token) - 1); return false; }
    return true;
  });
}

export function formatMarkers(text) {
  const types = [];
  if (/^\s{0,3}#{1,6}\s+\S/m.test(text)) types.push('标题');
  if (/^\s*[-*+]\s+\S/m.test(text) || /^\s*\d+[.)]\s+\S/m.test(text)) types.push('列表');
  if (/```|~~~/.test(text)) types.push('代码围栏');
  if (/\*\*[^*\n]+\*\*|__[^_\n]+__/.test(text)) types.push('加粗');
  if (/^\s*\|?\s*:?-{3,}:?\s*\|/m.test(text)) types.push('表格');
  return types;
}

export function analyze(record) {
  const findings = [];
  const add = (code, detail, original, rewrite) => findings.push({ code, title: RULES[code], detail, original: clip(original), rewrite: clip(rewrite) });
  const beforeNumbers = numericTokens(record.original);
  const afterNumbers = numericTokens(record.rewrite);
  const removed = difference(beforeNumbers, afterNumbers);
  const added = difference(afterNumbers, beforeNumbers);
  if (removed.length || added.length) add('numbers', '按数字及紧邻单位做词面比较，计入重复次数；换算、删去中间过程或修正原答案也会触发。', removed.join('、') || '无移除', added.join('、') || '无新增');

  const missing = (record.must_keep || []).filter(term => !normalize(record.rewrite).includes(normalize(term)));
  if (missing.length) add('anchors', '这些短语由数据提供者指定；同义改写也可能触发，请结合输入确认。', missing.map(term => normalize(record.original).includes(normalize(term)) ? term : term + '（原答案也未找到）').join('；'), '未找到指定短语');

  const lostConditions = CONDITION_GROUPS.map(([label, terms]) => ({ label, before: signals(record.original, terms), after: signals(record.rewrite, terms) })).filter(group => group.before.length && !group.after.length);
  if (lostConditions.length) add('conditions', '原答案含有以下条件或范围词，改写中未找到同组线索：' + lostConditions.map(x => x.label).join('、') + '。这不等同于条件已被删去。', lostConditions.map(x => x.before[0].excerpt).join('；'), record.rewrite);

  const uncertainty = signals(record.original, UNCERTAINTY);
  if (uncertainty.length && !signals(record.rewrite, UNCERTAINTY).length) {
    const assertion = signals(record.rewrite, ASSERTION);
    add('certainty', '原答案含有不确定性或频率限定词，改写中未找到。' + (assertion.length ? '改写还出现了较强的断言词。' : '请检查确定性是否发生变化。'), uncertainty[0].excerpt, assertion[0]?.excerpt || record.rewrite);
  }

  const clarification = signals(record.original, CLARIFICATION);
  if (clarification.length && !signals(record.rewrite, CLARIFICATION).length) add('clarification', '原答案含有澄清或索取信息的词语，改写中未找到。请确认最终训练输入是否足以支持直接作答。', clarification[0].excerpt, record.rewrite);

  const beforeLength = textLength(record.original);
  const afterLength = textLength(record.rewrite);
  if (beforeLength >= 24 && afterLength / beforeLength < 0.5) add('length', '非空白字符从 ' + beforeLength + ' 减至 ' + afterLength + '，低于原长度的 50%。短答案可能合适；请核对任务是否要求解释。', record.original, record.rewrite);

  const beforeFormat = formatMarkers(record.original);
  const afterFormat = formatMarkers(record.rewrite);
  const lostFormat = difference(beforeFormat, afterFormat);
  const newFormat = difference(afterFormat, beforeFormat);
  if (lostFormat.length || newFormat.length) add('format', '只识别标题、列表、代码围栏、加粗和表格的常见写法。格式变化是否符合目标，取决于任务要求。', beforeFormat.join('、') || '无已识别标记', afterFormat.join('、') || '无已识别标记');
  return findings;
}

export function parseRecords(text) {
  const source = text.replace(/^\uFEFF/, '');
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > MAX_REPORT_BYTES) throw new Error('文件超过 64 MiB。普通数据最多 5 MiB，导出的审核记录最多 64 MiB。');
  let parsed;
  if (bytes > MAX_BYTES) {
    try { parsed = JSON.parse(source); } catch { throw new Error('普通数据超过 5 MiB，请拆成较小批次。'); }
    if (!parsed || parsed.schema !== SCHEMA || !Array.isArray(parsed.records)) throw new Error('普通数据超过 5 MiB，请拆成较小批次。');
  }
  if (!source.trim()) throw new Error('请先粘贴数据、选择文件，或载入示例。');
  let values;
  let labels;
  if (parsed === undefined) {
    try { parsed = JSON.parse(source); } catch { /* JSONL is handled separately. */ }
  }
  if (parsed !== undefined) {
    if (Array.isArray(parsed)) values = parsed;
    else if (parsed && Array.isArray(parsed.records)) {
      if (parsed.schema && parsed.schema !== SCHEMA) throw new Error('审核记录版本不支持：' + parsed.schema);
      values = parsed.records;
    } else values = [parsed];
    labels = values.map((_, index) => '第 ' + (index + 1) + ' 条');
  } else {
    values = []; labels = [];
    source.split(/\r?\n/).forEach((line, index) => {
      if (!line.trim()) return;
      try { values.push(JSON.parse(line)); labels.push('第 ' + (index + 1) + ' 行'); }
      catch { throw new Error('第 ' + (index + 1) + ' 行不是有效 JSON。JSONL 需要每行一个完整对象；JSON 数组请检查括号和逗号。'); }
    });
  }
  if (!values.length) throw new Error('数据中没有样本。');
  if (values.length > MAX_RECORDS) throw new Error('单次最多 5000 条，请拆成较小批次。');
  const ids = new Set();
  return values.map((record, index) => {
    const fail = message => { throw new Error(labels[index] + '：' + message); };
    if (!record || typeof record !== 'object' || Array.isArray(record)) fail('需要一个对象。');
    for (const key of ['input', 'original', 'rewrite']) {
      if (typeof record[key] !== 'string' || !record[key].trim()) fail(key + ' 必须是非空文本。');
      if (record[key].length > 100000) fail(key + ' 超过 100000 个字符，请缩短或拆分。');
    }
    if (record.id !== undefined && typeof record.id !== 'string' && !(typeof record.id === 'number' && Number.isFinite(record.id))) fail('id 需要是文本或有限数字。');
    const id = record.id === undefined ? 'row-' + (index + 1) : String(record.id).trim();
    if (!id || id.length > 120) fail('id 需要为 1–120 个字符。');
    if (ids.has(id)) fail('id 重复：' + id);
    ids.add(id);
    if (record.must_keep !== undefined && (!Array.isArray(record.must_keep) || record.must_keep.length > 20 || record.must_keep.some(term => typeof term !== 'string' || !term.trim() || term.length > 500))) fail('must_keep 需要是短语数组，最多 20 项，每项 1–500 个字符。');
    const review = record.review ?? { decision: 'pending', note: '' };
    if (!review || typeof review !== 'object' || Array.isArray(review) || !Object.hasOwn(DECISIONS, review.decision ?? 'pending')) fail('review.decision 需要是 pending、keep、revise 或 hold。');
    if (review.note !== undefined && (typeof review.note !== 'string' || review.note.length > 10000)) fail('review.note 需要是文本，最多 10000 个字符。');
    return {
      id, input: record.input, original: record.original, rewrite: record.rewrite,
      must_keep: (record.must_keep || []).map(term => term.trim()),
      review: { decision: review.decision ?? 'pending', note: review.note ?? '' },
    };
  });
}

export function makeReport(records, now = new Date()) {
  return { schema: SCHEMA, tool_version: VERSION, exported_at: now.toISOString(), records: records.map(record => ({ ...record, review: { ...record.review }, findings: analyze(record) })) };
}
