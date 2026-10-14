# Release notes

## 0.1.0 — 2026-10-14

Pano brings a horizontal clipboard card strip to the native Omarchy shell.
Search text, code, colors, links, images, emoji and supported file references;
pin cards at the front or save favorites independently of ordinary retention.

- Compact previews, relative copy times, pin/favorite/delete actions and a
  centered settings page. Narrow displays use a vertical list.
- Touchpad sensitivity and bounded momentum, with one handler per wheel event.
  Keyboard focus selects the card used by Ctrl+P and other selection shortcuts.
- Optional recent colors, code-language badges and type-filter buttons, all
  disabled by default. Optional link titles load in the background.
- Exact selected-MIME payload storage, deduplication, persistent or session-only
  history, Incognito and supported sensitive-content hints.
- Native theme controls, keyboard navigation, search and combined filters.

Tested with Omarchy 4.0.4-1, Quickshell 0.3.1 and wl-clipboard 2.3.0.
Requires the Quattro shell plugin framework. Follow the README to disable the
built-in clipboard watcher before enabling Pano and configure the shortcut.

Known limits: one MIME representation is retained per entry; KDE multi-MIME
file-cut offers are skipped. Payloads cap at 32 MiB and searchable text at 8192
characters. App exclusions are unavailable. Automatic paste depends on the
receiving app accepting Shift+Insert. See the README for privacy, cleanup,
format details and remaining native checks. This release has no data migration.
