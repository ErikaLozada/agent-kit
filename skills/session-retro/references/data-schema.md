# Retro page data

One JSON object. Strings may contain inline HTML (`<code>`, `<strong>`, `<em>`, `<a>`); they are written by the
agent, never by viewers. Notes are keyed by `id`, so ids must be unique and stable across rebuilds (a changed id
orphans the owner's note).

```json
{
  "title": "Retrospective · requirements to first deployed draft",
  "storageKey": "<project>-retro-<date>",
  "notesFile": "retro-notes-<date>",
  "footer": "Built with the session-retro kit from <code>metrics.json</code> …",
  "sections": [ <section>, … ]
}
```

## Section

```json
{ "id": "glance", "title": "At a glance", "nav": "Glance", "lede": "One sentence.",
  "note": true,
  "blocks": [ <block>, … ] }
```

- `note`: `true` adds a note control for the whole section; a string sets its placeholder.
- `nav`: short label for the top navigation; `false` hides the section from it.
- A section with a single block may put the block's fields on the section itself (`"type": "prose", …`).
- Any block may have `heading` (an h3 above it) and `caption` (small text below).

## Blocks

| type | fields | items |
| --- | --- | --- |
| `prose` | `paragraphs: [html]` | |
| `list` | `ordered?: bool`, `items: [html]` | |
| `kpis` | `items` | `{label, value, unit?, sub?}` (6 per row on desktop) |
| `stack` | `unit`, `segments` | `{label, value, tone}`; tone is `model`, `tool`, `human` or `other`. One stacked bar with legend and direct labels: use it for the human / model / tool split. |
| `bars` | `unit`, `items` | `{label, value, detail?, hot?}`; horizontal bars sorted as given; `hot` marks the ones that matter |
| `timeline` | `items` | `{time, name, dur?, body?, hot?, kind?: "human", id?}` |
| `table` | `columns: [{label, num?}]`, `rows: [[html]]` | |
| `findings` | `items`, `numbered?` | `{id, title, severity?: high/medium/low, minutes?, body, evidence?, fix?}` |
| `claims` | `items` | `{id, claim, verdict: holds/partly/wrong/unverified, finding, evidence?}` |
| `qa` | `items` | `{q, a, id?}` |

## Suggested section order

1. `how`: what the page answers, the window, the sources, whether this is a self-review.
2. `glance`: KPIs plus a `stack` of human / model / tool to the milestone.
3. `answer`: the direct answer to the owner's question, in five lines or fewer.
4. `timeline`: the phases to the milestone, human stops marked `kind: "human"`.
5. `time`: `bars` by activity, a table of turns, latency and context.
6. `findings`: ranked causes, each with minutes, evidence and the change.
7. `claims`: only when reviewing another retro.
8. `changes`: ranked changes, minutes saved, and which file in which repo.
9. `worth`: what earned its time.
10. `method`: how it was measured and what the limits are.
