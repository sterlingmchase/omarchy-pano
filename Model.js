// UI projection only: stable payload IDs keep a live search from copying a new row.
var types = ['All', 'Code', 'Text', 'Color', 'Image', 'Link', 'File', 'Emoji']
function rows(entries, query, type, favorites) {
  var needle = String(query || '').toLowerCase()
  return entries.filter(function(e) {
    return (!favorites || e.favorite) && (type === 'All' || e.kind === type.toLowerCase()) &&
      (!needle || (e.searchText || (e.preview + ' ' + (e.language || '')).toLowerCase()).indexOf(needle) >= 0)
  })
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
if (typeof module !== 'undefined') module.exports = {rows: rows, palette: palette, age: age, types: types, typeIcon: typeIcon}
