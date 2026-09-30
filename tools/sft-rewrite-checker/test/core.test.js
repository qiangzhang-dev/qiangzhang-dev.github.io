import test from 'node:test';
import assert from 'node:assert/strict';
import { analyze, numericTokens, parseRecords, makeReport, MAX_BYTES } from '../core.js';
import { EXAMPLES } from '../examples.js';

const record = (original, rewrite, extra = {}) => ({ id: 'case', input: '请根据提供的信息回答。', original, rewrite, must_keep: [], review: { decision: 'pending', note: '' }, ...extra });
const codes = value => analyze(value).map(finding => finding.code);

test('shipping example surfaces removed numbers and scope cues without a quality score', () => {
  const findings = analyze(EXAMPLES[0]);
  assert.ok(findings.some(x => x.code === 'conditions' && x.original.includes('不计入')));
  assert.ok(findings.some(x => x.code === 'numbers' && x.original.includes('190元')));
  assert.equal(Object.hasOwn(findings[0], 'score'), false);
});

test('equivalent unit conversion is flagged as a lexical difference', () => {
  const findings = analyze(EXAMPLES[4]);
  assert.deepEqual(findings.map(x => x.code), ['numbers']);
  assert.equal(findings[0].original, '1000米');
  assert.equal(findings[0].rewrite, '1公里');
});

test('percent and percentage points remain distinct', () => {
  assert.ok(codes(EXAMPLES[5]).includes('numbers'));
});

test('numbers next to Chinese text, negative signs and full-width symbols are read', () => {
  assert.deepEqual(numericTokens('从４０％降到２０％，净变化−20个百分点，温度-3度。'), ['40%', '20%', '-20个百分点', '-3度']);
});

test('commas, whitespace and full-width digits normalize while repeated values count', () => {
  assert.deepEqual(numericTokens('１，０００ 米，1000米'), ['1000米', '1000米']);
  assert.ok(codes(record('5 件，加上另外 5 件。', '共 5 件。')).includes('numbers'));
  assert.equal(codes(record('5 件与 8 件。', '8件和5件。')).includes('numbers'), false);
});

test('same facts with different wording can produce no cues', () => {
  assert.deepEqual(analyze(EXAMPLES[7]), []);
});

test('scope synonyms in the cue dictionary do not imply a lost exclusion', () => {
  assert.equal(codes(record('运费不计入门槛。', '运费不算。')).includes('conditions'), false);
});

test('English cue words need word boundaries', () => {
  assert.deepEqual(analyze(record('This is a gift.', 'That gift is yours.')), []);
  assert.ok(codes(record('If the server is ready, retry.', 'Retry now.')).includes('conditions'));
});

test('certainty cues detect a hedged diagnosis becoming an assertion', () => {
  assert.ok(codes(EXAMPLES[2]).includes('certainty'));
  assert.equal(codes(record('不可能是这个原因。', '不是这个原因。')).includes('certainty'), false);
  assert.equal(codes(record('可能是网络问题。', '或许是网络问题。')).includes('certainty'), false);
});

test('clarification loss and newly added Markdown have separate cues', () => {
  assert.ok(codes(EXAMPLES[3]).includes('clarification'));
  assert.deepEqual(codes(EXAMPLES[6]), ['format']);
});

test('explicit anchors can expose an omitted condition, including an invalid original', () => {
  const first = analyze(record('运费不计入门槛。', '不能使用。', { must_keep: ['运费不计入门槛'] }));
  assert.ok(first.some(x => x.code === 'anchors'));
  const second = analyze(record('暂时无法回答。', '不能使用。', { must_keep: ['只在周末'] }));
  assert.ok(second.find(x => x.code === 'anchors').original.includes('原答案也未找到'));
});

test('large shortening is a review cue, not a claim of reasoning damage', () => {
  const finding = analyze(EXAMPLES[1]).find(x => x.code === 'length');
  assert.ok(finding.detail.includes('短答案可能合适'));
});

test('JSON arrays, JSONL with blank lines, BOM and a single JSON object import', () => {
  const item = EXAMPLES[7];
  assert.equal(parseRecords(JSON.stringify([item]))[0].id, item.id);
  assert.equal(parseRecords('\uFEFF\n' + JSON.stringify(item) + '\n\n')[0].rewrite, item.rewrite);
  assert.equal(parseRecords(JSON.stringify(item)).length, 1);
  assert.equal(parseRecords(JSON.stringify({ input: '问题', original: '原答', rewrite: '改写' }))[0].id, 'row-1');
});

test('schema validation reports the physical JSONL line and rejects the whole input', () => {
  assert.throws(() => parseRecords('\n' + JSON.stringify(EXAMPLES[7]) + '\n{broken}'), /第 3 行/);
  assert.throws(() => parseRecords(JSON.stringify([{ input: '问题', original: '答案' }])), /第 1 条.*rewrite/);
  assert.throws(() => parseRecords(JSON.stringify([{ ...EXAMPLES[7], input: ['问题'] }])), /input 必须/);
  assert.throws(() => parseRecords(JSON.stringify([EXAMPLES[7], EXAMPLES[7]])), /id 重复/);
  assert.throws(() => parseRecords('[]'), /没有样本/);
});

test('unexpected review values and malformed anchor lists cannot bypass validation', () => {
  assert.throws(() => parseRecords(JSON.stringify({ ...EXAMPLES[7], review: { decision: 'constructor' } })), /review.decision/);
  assert.throws(() => parseRecords(JSON.stringify({ ...EXAMPLES[7], must_keep: [null] })), /must_keep/);
  assert.throws(() => parseRecords(JSON.stringify({ ...EXAMPLES[7], review: { note: 5 } })), /review.note/);
});

test('file and record limits reject excessive inputs', () => {
  assert.throws(() => parseRecords(' '.repeat(MAX_BYTES + 1)), /5 MiB/);
  const tooMany = Array.from({ length: 5001 }, (_, i) => ({ ...EXAMPLES[7], id: String(i) }));
  assert.throws(() => parseRecords(JSON.stringify(tooMany)), /5000/);
});

test('export and reimport retain pairs, human decisions and notes; findings are recomputed', () => {
  const records = parseRecords(JSON.stringify(EXAMPLES));
  records[0].review = { decision: 'revise', note: '补回运费排除条件。' };
  const report = makeReport(records, new Date('2026-09-30T06:00:00Z'));
  report.records[0].findings = [{ code: 'fake', title: '伪造判断' }];
  const restored = parseRecords(JSON.stringify(report));
  assert.deepEqual(restored, records);
  assert.equal(makeReport(restored).records[0].findings.some(x => x.code === 'fake'), false);
  assert.throws(() => parseRecords(JSON.stringify({ schema: 'future/v9', records })), /版本不支持/);
});

test('HTML-like user text remains literal data through an export round trip', () => {
  const payload = '<img src=x onerror="alert(1)">';
  const records = [record(payload, payload)];
  assert.equal(parseRecords(JSON.stringify(makeReport(records)))[0].rewrite, payload);
});

test('review reports may exceed the raw data limit because they include notes and findings', () => {
  const records = Array.from({ length: 100 }, (_, i) => record('原答案。', '改写答案。', { id: String(i), input: 'x'.repeat(60000) }));
  assert.throws(() => parseRecords(JSON.stringify(records)), /5 MiB/);
  const report = makeReport(records);
  assert.equal(parseRecords(JSON.stringify(report)).length, 100);
});
