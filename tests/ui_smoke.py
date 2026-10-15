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
    # Mock only audio dispatch; keep the preference, success and overlap gates.
    source = re.sub(r'    Process \{\n        id: copySound\n.*?\n    \}\n(?=    Process \{\n        id: copier)',
                    '    QtObject { id: copySound; property bool running: false; onRunningChanged: if (running) root.qaSoundRequests++ }\n'
                    '    QtObject { id: pasteSound; property bool running: false; onRunningChanged: if (running) root.qaPasteRequests++ }\n', source, flags=re.S)
    source = source.replace('integrationEnabled && !player.running', '!player.running')
    source = source.replace('if (!watcher.running) playSound', 'if (!qaWatcherRunning) playSound')
    source = source.replace('    function enqueue(action, argument) {', '    function enqueue(action, argument) {\n        if (action === "delete") qaDeleteDispatches++; if (action === "pin") qaPinnedId = argument')
    source = source.replace('    function open(payload) {', '''    property int qaDeleteDispatches: 0
    property string qaPinnedId: ""
    property int qaSoundRequests: 0
    property int qaPasteRequests: 0
    property bool qaWatcherRunning: false
    function qaSize(width) { panel.width = width }
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
        if (item && item.scale !== 1) throw new Error("Card hover must preserve border size")
        if (horizontal) {
            if (surface.height > Style.space(400)) throw new Error("Strip is too tall: " + surface.height + ", panel: " + panel.width + "x" + panel.height + ", settings: " + settingsOpen)
            if (Math.abs(surface.y + surface.height - panel.height + Style.gapsOut) > 1) throw new Error("Strip must be at bottom")
            if (item && item.height > item.width * 1.35) throw new Error("Cards must be compact, not columns")
            if (item && edgeGlow.height !== item.height) throw new Error("Edge glow must match card height")
            if (item && cards.height - item.height > 1) throw new Error("Unused space below horizontal cards")
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
    function qaWheel(delta, phase, pixels) {
        wheelCards({pixelDelta: Qt.point(pixels ? delta : 0, 0), angleDelta: Qt.point(pixels ? 0 : delta, 0), phase: phase, device: null, accepted: false})
    }
    function qaEdges() {
        stopScrolling()
        cards.contentX = 0
        scrollCards(-1000)
        if (edgePull <= Style.space(24) || edgePull > Style.space(32) || !edgeGlow.visible || cards.contentX !== 0)
            throw new Error("Beginning must show bounded elastic feedback")
        if (cards.contentItem.transform[0].x !== edgePull || edgeGlow.opacity < 0.4)
            throw new Error("Elastic feedback must translate cards and light the edge")
        cards.contentX = cards.contentWidth - cards.width
        scrollCards(1000)
        if (edgePull >= 0 || Math.abs(edgePull) > Style.space(32))
            throw new Error("End feedback must pull in the opposite direction")
        scrollCards(-20)
        if (edgePull !== 0 || edgeReturn.running) throw new Error("Reversal must clear feedback")
        cards.contentX = 0
        scrollCards(-20)
    }
    function qaEdgeReset() {
        if (Math.abs(edgePull) > 0.1 || edgeReturn.running) throw new Error("Edge feedback must settle")
        scrollCards(-20)
        settingsOpen = true
        if (edgePull !== 0 || edgeReturn.running) throw new Error("Settings must clear edge feedback")
        settingsOpen = false
        var saved = entries
        entries = entries.slice(0, 1)
        cards.forceLayout()
        scrollCards(-100)
        if (edgePull !== 0) throw new Error("Short histories must not bounce")
        entries = saved
        prefs = Object.assign({}, prefs, {horizontal: false})
        cards.forceLayout()
        edgeFeedback(20)
        if (edgePull !== 0) throw new Error("Vertical layout must not bounce horizontally")
        prefs = Object.assign({}, prefs, {horizontal: true})
        cards.forceLayout()
        cards.contentX = cards.contentWidth - cards.width - 2
        cards.flick(-1000, 0)
    }
    function qaEdgeSettled() { return !edgeReturn.running && Math.abs(edgePull) < 0.1 }
    function qaEdgeCoast() {
        if (!cards.atXEnd || edgePull >= 0 || !edgeGlow.visible)
            throw new Error("Native momentum reaching the end must light the edge")
        stopScrolling()
        if (edgePull !== 0 || edgeReturn.running) throw new Error("Stopping must clear edge feedback")
        cards.contentX = 0
    }
    function qaMomentum() {
        stopScrolling()
        cards.contentX = 100
        qaWheel(-12, Qt.ScrollUpdate, true)
        if (cards.contentX <= 112) throw new Error("Touchpad sensitivity was not increased")
        if (Math.abs(wheelVelocity) > cards.maximumFlickVelocity) throw new Error("Unbounded momentum")
        qaWheel(0, Qt.ScrollEnd, true)
        if (!cards.flicking) throw new Error("Release did not start native momentum")
        qaWheel(12, Qt.ScrollUpdate, true)
        if (cards.flicking || wheelVelocity <= 0) throw new Error("Reversal did not stop the old glide")
        finishScroll()
        select(1)
        if (cards.flicking || wheelIdle.running) throw new Error("Keyboard navigation did not stop momentum")
        cards.contentX = 100
        qaWheel(-120, Qt.NoScrollPhase, false)
        if (cards.contentX <= 100 || cards.flicking || wheelIdle.running) throw new Error("Mouse wheel must remain direct")
        qaWheel(-12, Qt.ScrollMomentum, true)
        qaWheel(0, Qt.ScrollEnd, true)
        if (cards.flicking) throw new Error("System momentum received a second glide")
        qaWheel(-12, Qt.ScrollUpdate, true)
        lastWheelTime = Date.now() - 200
        finishScroll()
        if (cards.flicking) throw new Error("Stale gesture started momentum")
        cards.contentX = cards.contentWidth - cards.width
        qaWheel(-1000, Qt.ScrollUpdate, true)
        finishScroll()
        if (cards.contentX > cards.contentWidth - cards.width + 1) throw new Error("Momentum exceeded end")
        stopScrolling()
        cards.contentX = 100
        qaWheel(-12, Qt.ScrollUpdate, true)
        finishScroll()
        settingsOpen = true
        if (cards.flicking || wheelIdle.running) throw new Error("Settings did not stop momentum")
        settingsOpen = false
        qaWheel(-12, Qt.ScrollUpdate, true)
        finishScroll()
        query = "Python"
        if (cards.flicking || wheelIdle.running) throw new Error("Search did not stop momentum")
        query = ""
    }
    function qaPin() {
        selectedIndex = 0
        cards.forceLayout()
        var focused = cards.itemAtIndex(1)
        focused.forceActiveFocus()
        if (!focused.activeFocus) throw new Error("Card did not receive keyboard focus")
        key({key: Qt.Key_P, modifiers: Qt.ControlModifier, accepted: false})
        if (qaPinnedId !== focused.modelData.id) throw new Error("Ctrl+P must pin the focused card")
        search.forceActiveFocus()

        entries = entries.slice(0, 3)
        cards.forceLayout()
        var movedCard = cards.itemAtIndex(2)
        selectedIndex = 2
        var pinned = entries.map(function(e) { return Object.assign({}, e, {pinnedAt: e.id === "ccc" ? 20 : 0}) })
        applyState(JSON.stringify({settings: prefs, entries: pinned, directory: directory, captureAllowed: true}))
        if (filtered[0].id !== "ccc" || selectedIndex !== 0 || selectedEntry.id !== "ccc") throw new Error("Pin must move selected card to front without changing selection")
        cards.forceLayout()
        if (cards.itemAtIndex(0) !== movedCard) throw new Error("Pin must move the existing card instead of rebuilding it")
        if (!qaFind(qaFind(movedCard, "pinAction"), "togglePop").running) throw new Error("Pin update must animate its icon")
        var newer = Object.assign({}, entries[0], {id: "newer", pinnedAt: 0})
        applyState(JSON.stringify({settings: prefs, entries: [newer].concat(entries), directory: directory, captureAllowed: true}))
        if (filtered[0].id !== "ccc" || selectedEntry.id !== "ccc") throw new Error("New copies must stay behind pins")
        var unpinned = entries.map(function(e) { return Object.assign({}, e, {pinnedAt: 0}) })
        applyState(JSON.stringify({settings: prefs, entries: unpinned, directory: directory, captureAllowed: true}))
        if (filtered[0].id !== "newer" || selectedEntry.id !== "ccc") throw new Error("Unpin must restore recency and keep selected ID")
    }
    function qaSettings() {
        var previous = [query, typeFilter, favoritesOnly].join("|")
        settingsOpen = true
        content.children[0].ensurePolished()
        if (search.visible || paletteFlow.visible || filterFlow.visible || historyActions.visible || cards.visible)
            throw new Error("History controls must be hidden in Settings")
        if (!settingsHeader.visible || !settingsView.visible || !backToHistory.visible)
            throw new Error("Settings needs its own heading and Back control")
        if (Math.abs(surface.y - (panel.height - surface.height) / 2) > 1)
            throw new Error("Settings must stay centered")
        if (settingsView.height < Style.space(80)) throw new Error("Settings content is clipped")
        var copyPreview = qaFind(settingsColumn, "copySoundPreview")
        var pastePreview = qaFind(settingsColumn, "pasteSoundPreview")
        if (!copyPreview || !pastePreview || !copyPreview.visible || !pastePreview.visible)
            throw new Error("Both sound settings need preview buttons")
        var copyToggle = qaFind(settingsColumn, "copySoundToggle")
        var pasteToggle = qaFind(settingsColumn, "pasteSoundToggle")
        if (copyPreview.x + copyPreview.width > copyToggle.x || pastePreview.x + pastePreview.width > pasteToggle.x)
            throw new Error("Sound preview buttons must be left of their toggles")
        var previousPrefs = prefs
        prefs = Object.assign({}, prefs, {copySound: false, pasteSound: false})
        var unchanged = JSON.stringify(prefs)
        copySound.running = false
        pasteSound.running = false
        copyPreview.clicked()
        pastePreview.clicked()
        if (!copySound.running || !pasteSound.running || JSON.stringify(prefs) !== unchanged)
            throw new Error("Preview buttons must play while disabled without changing toggles")
        if (copyPreview.mapToItem(settingsColumn, 0, 0).x + copyPreview.width > settingsColumn.width + 1)
            throw new Error("Sound preview control overflows narrow settings")
        copySound.running = false
        pasteSound.running = false
        prefs = previousPrefs
        search.focus = false
        backToHistory.forceActiveFocus()
        var deletes = qaDeleteDispatches
        key({key: Qt.Key_Delete, modifiers: Qt.NoModifier, accepted: false})
        if (qaDeleteDispatches !== deletes) throw new Error("Delete in Settings must not delete a hidden history entry")
        key({key: Qt.Key_Escape, modifiers: Qt.NoModifier, accepted: false})
        content.children[0].ensurePolished()
        if (settingsOpen || !historyHeader.visible || !historyActions.visible || !cards.visible)
            throw new Error("Escape must return to history")
        if ([query, typeFilter, favoritesOnly].join("|") !== previous)
            throw new Error("Settings must preserve search and filters")
    }
    function qaFind(item, name) {
        if (item.objectName === name) return item
        var children = item.data || []
        for (var i = 0; i < children.length; i++) {
            var found = qaFind(children[i], name)
            if (found) return found
        }
        return null
    }
    property var qaToggleButton: null
    function qaFeedback() {
        cards.forceLayout()
        var first = cards.itemAtIndex(0)
        qaToggleButton = qaFind(first, "favoriteAction")
        if (!qaToggleButton) throw new Error("Favorite action not found")
        var firstId = first.modelData.id
        entries = entries.map(function(entry) { return entry.id === firstId ? Object.assign({}, entry, {favorite: !entry.favorite}) : entry })
        if (!qaFind(qaToggleButton, "togglePop").running) throw new Error("Favorite update must animate its icon")
        if (!cards.move || !cards.displaced || !cards.remove || !cards.add) throw new Error("Missing native list transitions")
        copyId = colors[0].id
        copier.exited(1, 0)
        if (copiedColorId || copiedHint.running) throw new Error("Failed copy must not confirm success")
        errorText = ""
        copyEvent('{"copied":true}')
        copier.exited(0, 0)
        if (!opened || copiedColorId !== copyId || !copiedHint.running) throw new Error("Successful swatch copy must confirm and stay open")
    }
    function qaFeedbackSettled() { return !copiedHint.running }
    function qaSound() {
        var previous = prefs
        prefs = Object.assign({}, prefs, {copySound: false})
        copyId = "synthetic-non-color-entry"
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== 0) throw new Error("Disabled sound must stay silent")
        prefs = Object.assign({}, prefs, {copySound: true})
        copier.exited(1, 0)
        if (qaSoundRequests !== 0) throw new Error("Failed copy must stay silent")
        opened = false
        copyEvent("malformed helper message")
        if (qaSoundRequests !== 0) throw new Error("Malformed messages must stay silent")
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== 1) throw new Error("Successful non-color copy must pop after the overlay closes")
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== 1) throw new Error("Copy sounds must not overlap")
        copySound.running = false
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== 2) throw new Error("Later copies must be able to pop again")
        copySound.running = false
        prefs = Object.assign({}, prefs, {copySound: false})
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== 2) throw new Error("Live sound disable must apply immediately")
        prefs = Object.assign({}, prefs, {pasteSound: true})
        copyPaste = false
        copier.exited(0, 0)
        if (qaPasteRequests !== 0) throw new Error("Copy-only selections must not make a paste sound")
        copyPaste = true
        copier.exited(1, 0)
        if (qaPasteRequests !== 0) throw new Error("Failed auto-paste must stay silent")
        copier.exited(0, 0)
        if (qaPasteRequests !== 1) throw new Error("Successful auto-paste must play its own sound")
        copier.exited(0, 0)
        if (qaPasteRequests !== 1) throw new Error("Paste sounds must not overlap")
        pasteSound.running = false
        prefs = Object.assign({}, prefs, {pasteSound: false, copySound: true})
        copyEvent('{"copied":true}')
        copier.exited(0, 0)
        if (qaPasteRequests !== 1 || qaSoundRequests !== 3) throw new Error("Copy and paste sound settings must be independent")
        copySound.running = false
        prefs = Object.assign({}, prefs, {pasteSound: true})
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== 4 || qaPasteRequests !== 1) throw new Error("Copy confirmation must precede paste feedback")
        copier.exited(0, 0)
        if (qaPasteRequests !== 2) throw new Error("Both sounds must play for successful copy then paste")
        copySound.running = false
        pasteSound.running = false
        copyPaste = false
        prefs = previous
        opened = true
        errorText = ""
    }
    function qaFeedbackDone() {
        if (copiedColorId || Math.abs(qaToggleButton.scale - 1) > 0.001) throw new Error("Copy feedback and icon scale must settle")
        cards.forceLayout()
        var removed = cards.itemAtIndex(1)
        var id = removed.modelData.id
        entries = entries.filter(function(entry) { return entry.id !== id })
        cards.forceLayout()
        if (displayModel.count !== filtered.length || removed.enabled) throw new Error("Removed cards must leave the model and stop accepting input while fading")
    }
    function qaGlobalSound() {
        var previous = prefs
        var before = qaSoundRequests
        prefs = Object.assign({}, prefs, {copySound: true})
        qaWatcherRunning = true
        opened = false
        copySound.running = false
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== before) throw new Error("Pano selections must wait for the watcher to avoid double pops")
        clipboardEvent('{"captured":true}')
        if (qaSoundRequests !== before + 1) throw new Error("External clipboard captures must pop while Pano is closed")
        copyEvent('{"copied":true}')
        if (qaSoundRequests !== before + 1) throw new Error("Watcher plus own-copy confirmation must not double pop")
        copySound.running = false
        clipboardEvent("invalid")
        clipboardEvent('{"error":"synthetic failure"}')
        clipboardEvent('{}')
        if (qaSoundRequests !== before + 1) throw new Error("Unsupported or failed captures must stay silent")
        clipboardEvent('{"captured":true}')
        if (qaSoundRequests !== before + 2) throw new Error("Repeated clipboard copies must pop again")
        copySound.running = false
        prefs = Object.assign({}, prefs, {copySound: false, pasteSound: false})
        clipboardEvent('{"captured":true}')
        if (qaSoundRequests !== before + 2) throw new Error("Disabled global copy sound must stay silent")
        var saved = JSON.stringify(prefs)
        playSound("copy", true)
        playSound("paste", true)
        if (qaSoundRequests !== before + 3 || !pasteSound.running || JSON.stringify(prefs) !== saved)
            throw new Error("Sound previews must work with both toggles off without changing settings")
        copySound.running = false
        pasteSound.running = false
        prefs = previous
        qaWatcherRunning = false
        opened = true
    }
    property int qaStreamCopies: 0
    property int qaStreamPastes: 0
    property var qaStreamPrefs: null
    function qaProcessSound() {
        qaStreamPrefs = prefs
        prefs = Object.assign({}, prefs, {copySound: true, pasteSound: true})
        copySound.running = false
        pasteSound.running = false
        qaStreamCopies = qaSoundRequests
        qaStreamPastes = qaPasteRequests
        copyPaste = true
        opened = false
        copier.command = ["python3", "-c", "import json,time;print(json.dumps(dict(copied=True)),flush=True);time.sleep(.2)"]
        copier.running = true
    }
    function qaProcessSoundDone() {
        if (copier.running || qaSoundRequests !== qaStreamCopies + 1 || qaPasteRequests !== qaStreamPastes + 1)
            throw new Error("Real process stdout must trigger copy feedback before successful paste exit")
        copyPaste = false
        copySound.running = false
        pasteSound.running = false
        prefs = qaStreamPrefs
        opened = true
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
    property int edgeWaits: 0
    property int feedbackWaits: 0
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
                    pano.entries = pano.entries.concat(pano.entries, pano.entries).map(function(entry, index) { return index < 3 ? entry : Object.assign({}, entry, {id: entry.id + index}) })
                } else if (step === 18) {
                    pano.qaCheck(); pano.qaScroll(); pano.qaMomentum(); pano.qaEdges()
                } else if (step === 21) {
                    if (!pano.qaEdgeSettled() && edgeWaits++ < 10) return
                    pano.qaEdgeReset()
                } else if (step === 22) {
                    pano.qaEdgeCoast(); pano.qaPin(); pano.qaFeedback(); pano.qaSound(); pano.qaProcessSound()
                } else if (step === 23) {
                    if (!pano.qaFeedbackSettled() && feedbackWaits++ < 15) return
                    pano.qaProcessSoundDone(); pano.qaFeedbackDone(); pano.qaGlobalSound(); pano.qaSettings()
                    pano.qaSize(390); pano.settingsOpen = true
                } else if (step === 24) {
                    pano.qaSettings(); pano.qaConfirm()
                } else if (step === 25) {
                    pano.close()
                    if (pano.opened) throw new Error("Did not close")
                    console.log("PANO_UI_PASS: 16 layout/setting combinations, scrolling and elastic edges, persistent card identity/transitions, pin/star feedback, successful/failed copy confirmation, deletion input safety, keys, filters, settings, confirmation and close")
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
