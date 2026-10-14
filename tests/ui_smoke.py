#!/usr/bin/env python3
"""Run real Omarchy controls with a mocked offscreen window, never a watcher.

Only PanelWindow's Wayland host is substituted. No installed plugin is enabled.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OMARCHY = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
with tempfile.TemporaryDirectory(prefix='pano-ui-') as tmp:
    stage = Path(tmp)
    for name in ('Commons', 'Ui'):
        shutil.copytree(OMARCHY / 'shell' / name, stage / name)
    source = (ROOT / 'Pano.qml').read_text()
    source = source.replace('import QtQuick\n', 'import QtQuick\nimport QtQuick.Window\n')
    source = source.replace('    PanelWindow {', '    Window {\n        width: 1100; height: 700; contentItem.width: width; contentItem.height: height')
    source = source.replace('        panel.screen = target', '        // Offscreen mock: no native screen assignment.')
    source = re.sub(r'^        (?:anchors \{ top: true; bottom: true; left: true; right: true \}|exclusionMode:.*|WlrLayershell\..*)\n', '', source, flags=re.M)
    source = source.replace('    function open(payload) {', '''    function qaSize(width) { panel.width = width }
    function qaCheck() {
        content.children[0].ensurePolished()
        paletteFlow.parent.ensurePolished()
        filterFlow.ensurePolished()
        cards.forceLayout()
        if (surface.width > panel.width || search.width < Style.space(80)) throw new Error("Clipped search")
        if (cards.width < 1 || cards.height < Style.space(80)) throw new Error("No card space")
        if (filterFlow.visible !== prefs.filters) throw new Error("Filter visibility")
        if (paletteFlow.visible !== prefs.colors) throw new Error("Palette visibility")
        if (prefs.colors && (paletteFlow.width <= 0 || paletteFlow.height <= 0)) throw new Error("No palette area: " + paletteFlow.width + "x" + paletteFlow.height + ", children: " + paletteFlow.childrenRect + ", colors: " + colors.length + ", parent: " + paletteFlow.parent.width + "x" + paletteFlow.parent.height + ", window: " + panel.contentItem.width + "x" + panel.contentItem.height + ", opened: " + opened + ", visible: " + paletteFlow.visible + ", search: " + search.width + "x" + search.height)
        if (cards.count !== filtered.length) throw new Error("List projection")
        var item = cards.itemAtIndex(0)
        if (item && item.width > cards.width) throw new Error("Card overflow")
        if (horizontal) {
            if (surface.height > Style.space(400)) throw new Error("Strip is too tall: " + surface.height + ", panel: " + panel.width + "x" + panel.height + ", settings: " + settingsOpen)
            if (Math.abs(surface.y + surface.height - panel.height + Style.gapsOut) > 1) throw new Error("Strip must be at bottom")
            if (item && item.height > item.width * 1.35) throw new Error("Cards must be compact, not columns")
        }
    }
    function qaScroll() {
        content.children[0].ensurePolished()
        cards.forceLayout()
        if (cards.contentWidth <= cards.width) throw new Error("Scroll test needs overflow")
        scrollCards(120)
        if (cards.contentX <= 0) throw new Error("Horizontal scroll did not advance")
        scrollCards(100000)
        if (cards.contentX > cards.contentWidth - cards.width + 1) throw new Error("Scroll exceeded end")
        scrollCards(-100000)
        if (cards.contentX !== 0) throw new Error("Scroll exceeded start")
        key({key: Qt.Key_Right, modifiers: Qt.NoModifier, accepted: false})
        if (selectedIndex !== 1) throw new Error("Right arrow must select next card from empty search")
    }
    function qaConfirm() { confirm.opened = true }
    function open(payload) {''')
    (stage / 'Pano.qml').write_text(source)
    shutil.copy(ROOT / 'Model.js', stage)
    (stage / 'shell.qml').write_text('''import QtQuick
import Quickshell
import "." as Plugin
ShellRoot {
    Plugin.Pano { id: pano; integrationEnabled: false; shell: mockShell }
    QtObject { id: mockShell; function hide(id) { pano.close() } }
    property int step: -1
    Timer {
        interval: 120; running: true; repeat: true
        onTriggered: {
            try {
                if (step === -1) {
                    pano.entries = [
                        {id: "aaa", kind: "color", preview: "#ff000080", rgba: [1,0,0,.5], language: "", favorite: false, copiedAt: Date.now()/1000},
                        {id: "bbb", kind: "code", preview: "const message: string = 'hello';\\nconsole.log(message)", rgba: [], language: "TypeScript", favorite: true, copiedAt: Date.now()/1000-100},
                        {id: "ccc", kind: "text", preview: "Plain text\\n  preserves whitespace", rgba: [], language: "", favorite: false, copiedAt: Date.now()/1000-300}
                    ]
                    pano.ready = true
                    pano.open("")
                } else if (step < 16) {
                    if (step > 0) pano.qaCheck()
                    pano.qaSize(step < 8 ? 1100 : 390)
                    var mask = step % 8
                    pano.prefs = {colors: !!(mask & 1), languages: !!(mask & 2), filters: !!(mask & 4), previews: false, retention: 300, incognito: false, sessionOnly: false, paste: false, horizontal: true}
                } else if (step === 16) {
                    pano.qaCheck()
                    pano.typeFilter = "Code"; pano.query = "hello"; pano.favoritesOnly = true
                    if (pano.filtered.length !== 1) throw new Error("Combined filters")
                } else if (step === 17) {
                    pano.qaSize(1100); pano.query = ""; pano.typeFilter = "All"; pano.favoritesOnly = false
                    pano.entries = pano.entries.concat(pano.entries, pano.entries)
                } else if (step === 18) {
                    pano.qaCheck(); pano.qaScroll()
                    pano.qaSize(390); pano.settingsOpen = true
                } else if (step === 19) {
                    pano.settingsOpen = false; pano.qaConfirm()
                } else if (step === 20) {
                    pano.close()
                    if (pano.opened) throw new Error("Did not close")
                    console.log("PANO_UI_PASS: 16 layout/setting combinations, bottom strip geometry, horizontal scrolling, keys, filters, settings, confirmation and close")
                    Qt.quit()
                }
                step++
            } catch (error) { console.error("PANO_UI_FAIL: " + error); Qt.quit() }
        }
    }
}''')
    runtime = stage / 'runtime'
    runtime.mkdir(mode=0o700)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM='offscreen',
               QT_QPA_PLATFORMTHEME='generic', QT_QUICK_CONTROLS_STYLE='Basic', QT_QUICK_BACKEND='software')
    env.pop('WAYLAND_DISPLAY', None)
    result = subprocess.run(['quickshell', '-p', str(stage / 'shell.qml'), '--no-color'], env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
    print(result.stdout)
    assert 'PANO_UI_PASS' in result.stdout, 'UI smoke test did not pass'
    assert not re.search(r'PANO_UI_FAIL|Failed to load configuration|ReferenceError|TypeError|Binding loop|Invalid property|Unable to assign', result.stdout), 'QML errors'
