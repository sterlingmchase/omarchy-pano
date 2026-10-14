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
