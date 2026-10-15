// UI projection only: stable payload IDs keep a live search from copying a new row.
var types = ['All', 'Code', 'Text', 'Color', 'Image', 'Link', 'File', 'Emoji']
function sync(model, entries) {
  var wanted = new Set(entries.map(function(e) { return e.id }))
  for (var i = model.count - 1; i >= 0; i--)
    if (!wanted.has(model.get(i).entry.id)) model.remove(i)
  for (var target = 0; target < entries.length; target++) {
    var entry = entries[target]
    if (target < model.count && model.get(target).entry.id === entry.id) {
      model.setProperty(target, 'entry', entry)
      continue
    }
    var from = target + 1
    while (from < model.count && model.get(from).entry.id !== entry.id) from++
    if (from < model.count) {
      model.move(from, target, 1)
      model.setProperty(target, 'entry', entry)
    } else model.insert(target, {entry: entry})
  }
}
function rows(entries, query, type, favorites) {
  var needle = String(query || '').toLowerCase()
  return entries.filter(function(e) {
    return (!favorites || e.favorite) && (type === 'All' || e.kind === type.toLowerCase()) &&
      (!needle || (e.searchText || (e.preview + ' ' + (e.language || '')).toLowerCase()).indexOf(needle) >= 0)
  }).map(function(entry, index) { return {entry: entry, index: index} })
    .sort(function(a, b) { return (b.entry.pinnedAt || 0) - (a.entry.pinnedAt || 0) || a.index - b.index })
    .map(function(row) { return row.entry })
}
function palette(entries) {
  return entries.filter(function(e) { return e.kind === 'color' && e.rgba && e.rgba.length === 4 }).slice(0, 10)
}
function typeIcon(kind) {
  return {link: '󰌷', emoji: '󰞅', text: '󰈙', code: '󰅩', color: '󰏘', image: '󰋩', file: '󰈔'}[kind] || '󰈙'
}
function age(timestamp, now) {
  var seconds = Math.max(0, Math.floor(now / 1000 - timestamp))
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago'
  if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago'
  return Math.floor(seconds / 86400) + 'd ago'
}
if (typeof module !== 'undefined') module.exports = {sync: sync, rows: rows, palette: palette, age: age, types: types, typeIcon: typeIcon}
