# Marketplace release process

Target: **Pano Clipboard 0.1.0**, plugin ID `sterling.pano`.
The manifest keeps its original version for the first public release.

## Listing metadata

| Field | Value |
| --- | --- |
| Issue title | `[Plugin]: Pano Clipboard` |
| Repository URL | https://github.com/sterlingmchase/omarchy-pano |
| Category | Productivity |
| Tags | quickshell, hyprland |
| Preview | Root `preview.png`; synthetic clipboard entries, no personal history |
| License | MIT; original implementation, GNOME inspiration credited in README |

Maintainer notes to include with the submission:

> Native Quattro overlay with horizontal clipboard cards, pins, favorites,
> search, optional color swatches, language labels and type buttons. Tested on
> Omarchy 4.0.4-1 / Quickshell 0.3.1 / wl-clipboard 2.3.0. Manual setup is
> required: disable omarchy.clipboard before enabling sterling.pano and bind
> the invocation shortcut. Installing does not rewrite desktop configuration.
> Request manual-setup installation guidance so users see the watcher/shortcut
> requirements before enabling it. See README for dependency and MIME limits.

Use the [marketplace submission form](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml).
The [publishing guide](https://plugins.omarchy.org/publish.html) requires a
public repository, root manifest, README, license and safe removal instructions.
The [submission guide](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md)
defines the allowed category/tags, owner checklist and exact issue format.
The owner must review its checklist and approve the completed submission before
an issue is opened. Listing requires the marketplace's exact-commit checks and
maintainer approval; local validation does not grant a marketplace listing.

## Capabilities for reviewers

- Runs inside the existing Omarchy shell. QML starts short-lived Python helpers
  and one `wl-paste --watch` through `flock`, `setpriv` and `timeout`.
- Runtime tools: Python 3, wl-clipboard (`wl-paste`/`wl-copy`), util-linux
  (`flock`/`setpriv`) and coreutils (`timeout`). Optional `wtype` supplies
  automatic paste; optional Pygments expands language detection.
- Stores clipboard payloads and metadata in private user state directories;
  session-only history uses a private runtime directory. Cleanup is confined to
  plugin-owned resources. No root privileges, installers or downloaded code.
- Optional link titles use bounded HTTP(S) requests; disabled by default.
  Clipboard capture and optional paste are intentional desktop capabilities.
- Built-in watcher exclusion and a private lock prevent duplicate recording.
  See README for sensitive hints, unencrypted storage and session cleanup limits.

## Release checks

- [x] Root schema-1 manifest, namespaced ID, README and MIT license present.
- [x] Root preview contains synthetic data; README links to that preview.
- [x] Install, activation, shortcut, update, removal and rollback documented.
- [x] Automated storage/model, offscreen UI/wheel, QML and native validator checks
  pass locally. Native touchpad feel was also confirmed by the owner.

## Publishing procedure

1. Commit and push release files; review and merge to main.
2. Recheck the public default-branch snapshot and run the README checks.
3. Review the completed [submission body](marketplace-submission.md) with the
   owner and obtain approval before creating the marketplace issue.
4. Create tag/release `v0.1.0` at the approved main commit using CHANGELOG.md
   as release notes. Never tag an uncommitted working tree.
5. Submit the public repository and address exact-commit marketplace results.
   Wait for marketplace maintainer approval before claiming it is listed.

No custom binary, archive format or installer is needed: this installed Omarchy
uses Git repository installation. GitHub tags identify releases; `omarchy plugin
update` follows the default branch rather than a selected release tag. Keep main
installable. Do not advertise a marketplace install-by-ID command until the
installed CLI supports it.

The full native checklist remains in README. Automated clipboard/network tests
use mocks; UI tests use an offscreen host. Multi-monitor, scaling, screen-reader,
theme-switching and exhaustive native MIME/paste/lifecycle checks are not newly
verified by release preparation.
