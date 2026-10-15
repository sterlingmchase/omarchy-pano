const assert = require('node:assert/strict')
const M = require('../Model.js')
const entries = [
  {id: 'a', kind: 'code', language: 'Python', preview: 'print(123)', favorite: true},
  {id: 'b', kind: 'text', preview: 'print this page', favorite: false},
  {id: 'c', kind: 'color', preview: '#f008', rgba: [1,0,0,.5], favorite: true}
]
assert.deepEqual(M.rows(entries, 'print', 'Code', true).map(e => e.id), ['a'])
assert.equal(M.rows(entries, 'print', 'Text', true).length, 0)
assert.equal(M.rows(entries, '', 'All', false).length, 3)
assert.equal(M.rows(entries, 'python', 'Code', false).length, 1)
assert.equal(M.palette(entries).length, 1)
assert.equal(M.palette(entries.filter(e => e.id !== 'c')).length, 0)
assert.equal(M.palette(Array(20).fill(entries[2])).length, 10)
assert.equal(M.age(100, 110000), 'just now')
assert.equal(M.age(100, 200000), '1m ago')
console.log('model checks passed')

assert.ok(M.typeIcon('code'))
assert.notEqual(M.typeIcon('image'), M.typeIcon('text'))

const pinned = entries.map(e => ({...e, pinnedAt: e.id === 'b' ? 20 : e.id === 'c' ? 10 : 0}))
assert.deepEqual(M.rows(pinned, '', 'All', false).map(e => e.id), ['b', 'c', 'a'])
const withNewCopy = [{id: 'new', kind: 'text', preview: 'latest', favorite: false}, ...pinned]
assert.deepEqual(M.rows(withNewCopy, '', 'All', false).map(e => e.id), ['b', 'c', 'new', 'a'])
assert.deepEqual(M.rows(pinned, '', 'All', true).map(e => e.id), ['c', 'a'])
assert.deepEqual(M.rows(pinned, 'print', 'Code', false).map(e => e.id), ['a'])
assert.deepEqual(M.rows(pinned.map(e => ({...e, pinnedAt: e.id === 'b' ? 0 : e.pinnedAt})), '', 'All', false).map(e => e.id), ['c', 'a', 'b'])
assert.deepEqual(pinned.map(e => e.id), ['a', 'b', 'c'])

// Stand-in for Qt's ListModel; check edits and identity without rendering cards.
const data = []
let moves = 0
const model = {
  get count() { return data.length },
  get(i) { return data[i] },
  remove(i) { data.splice(i, 1) },
  insert(i, value) { data.splice(i, 0, value) },
  setProperty(i, name, value) { data[i][name] = value },
  move(from, to, count) { moves++; data.splice(to, 0, ...data.splice(from, count)) }
}
M.sync(model, entries)
const identities = data.slice()
M.sync(model, [pinned[2], pinned[0], pinned[1]])
assert.equal(moves, 1)
assert.equal(data[0], identities[2])
assert.deepEqual(data.map(row => row.entry.id), ['c', 'a', 'b'])
assert.equal(data[0].entry.pinnedAt, 10)
M.sync(model, [entries[0], {id: 'new', kind: 'text'}, entries[2]])
assert.deepEqual(data.map(row => row.entry.id), ['a', 'new', 'c'])
assert.equal(data[0], identities[0])
M.sync(model, [])
assert.equal(data.length, 0)
const large = Array.from({length: 5000}, (_, i) => ({id: String(i)}))
M.sync(model, large)
moves = 0
M.sync(model, [large[4999], ...large.slice(0, -1)])
assert.equal(moves, 1)
assert.equal(data[0].entry.id, '4999')
assert.equal(data.length, 5000)
