### Repository URL

https://github.com/sterlingmchase/omarchy-pano

### Category

Productivity

### Tags

quickshell, hyprland

### Suggest a missing tag

_No response_

### Maintainer notes

Pano Clipboard (`sterling.pano`) is a native Quattro overlay with a horizontal
clipboard card strip, pins, favorites, search, and optional color swatches,
language labels and type buttons. Release: v0.1.0. Tested on Omarchy 4.0.4-1,
Quickshell 0.3.1 and wl-clipboard 2.3.0. Root preview.png uses synthetic entries.

Manual setup is required: disable omarchy.clipboard before enabling sterling.pano
and configure the invocation shortcut. Please use manual-setup installation
guidance so users see those requirements before activation. The plugin does not
rewrite desktop configuration. Installation, removal and rollback are in README.

Uses Python 3, wl-clipboard, util-linux (flock/setpriv), and coreutils (timeout).
Pygments and wtype are optional. It records standard clipboard offers into
private user state/runtime directories; the helper and one clipboard watcher
run without root privileges. Optional bounded HTTP(S) link-title requests and
automatic paste are disabled by default. README documents sensitive MIME hints,
unencrypted history, session cleanup and single-MIME/file-cut limitations.

Local validation passes: native manifest validator, QML parser, 20 Python tests,
model checks, offscreen UI tests and Qt wheel-event tests. Clipboard/network unit
tests are mocked and offscreen tests do not establish full compositor coverage;
remaining native checks are documented. Touchpad feel was confirmed by the owner.

### Submission checklist

- [x] The repository is public and contains installation and removal instructions.
- [x] I have documented the plugin license and any external dependencies.
- [x] I confirm that I own or have permission to submit this plugin and its preview assets.
- [x] The plugin does not overwrite user configuration without explicit consent.
- [x] I understand that approval is for listing and is not a security review.
