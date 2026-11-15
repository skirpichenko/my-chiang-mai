export const meta = {
  name: 'catalog-extract',
  description: 'Extract catalog entries from the pending part files of the Telegram channel export, up to 4 parts per agent',
  phases: [
    { title: 'Extract', detail: 'one agent per group of up to 4 part files; each writes one JSONL per part' },
  ],
}

// args: the JSON printed by `python3 tools/catalog.py pending`, i.e. { root: '<absolute repo path>', pairs: [[part.txt, part.jsonl], ...] }
const ROOT = args.root
const PAIRS = args.pairs
const groups = []
for (let i = 0; i < PAIRS.length; i += 4) groups.push(PAIRS.slice(i, i + 4))

const SCHEMA = {
  type: 'object',
  properties: {
    parts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          posts_seen: { type: 'integer' },
          entries_written: { type: 'integer' },
          valid_jsonl: { type: 'boolean' },
        },
        required: ['file', 'posts_seen', 'entries_written', 'valid_jsonl'],
      },
    },
    notes: { type: 'string' },
  },
  required: ['parts'],
}

const prompt = g => `Read ${ROOT}/tools/extract_prompt.md in full and follow it exactly.

Your part files, in this order:
${g.map(([src, dst]) => `- ${src}  ->  write ${dst}`).join('\n')}

Return the structured result: for each part file its path, posts seen, entries written and whether the JSONL validated, plus short notes on anything ambiguous.`

phase('Extract')
const results = await parallel(groups.map((g, n) => () =>
  agent(prompt(g), { label: `extract:${n + 1}/${groups.length}`, phase: 'Extract', schema: SCHEMA })
    .then(r => ({ group: n, files: g.length, ...(r || { parts: [], notes: 'agent returned null' }) }))
))

const ok = results.filter(Boolean)
const incomplete = ok.filter(r => r.parts.length < r.files).map(r => r.group + 1)
const total = ok.flatMap(r => r.parts).reduce((s, p) => s + (p.entries_written || 0), 0)
log(`entries written: ${total}; incomplete groups: ${incomplete.join(', ') || 'none'}`)
return {
  total_entries: total,
  incomplete_groups: incomplete,
  invalid_files: ok.flatMap(r => r.parts).filter(p => !p.valid_jsonl).map(p => p.file),
  notes: ok.filter(r => r.notes).map(r => `group ${r.group + 1}: ${r.notes}`),
}
