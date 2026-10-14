import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import qs.Ui
import "Model.js" as Model

Item {
    id: root
    property var shell: null
    property var manifest: null
    property string omarchyPath: Quickshell.env("OMARCHY_PATH") || "/usr/share/omarchy"
    // Harnesses can disable all desktop I/O without altering the shipped plugin.
    property bool integrationEnabled: true
    readonly property string pluginId: "sterling.pano"
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("clipboard.py").toString().replace(/^file:\/\//, ""))
    readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/omarchy-pano"
    readonly property string sessionDir: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/omarchy-pano-" + sessionToken
    readonly property string sessionToken: Date.now().toString() + "-" + Math.random().toString(36).slice(2)
    property string directory: stateDir
    property bool opened: false
    property bool captureAllowed: false
    property bool ready: false
    property string errorText: ""
    property var entries: []
    property var prefs: ({colors: false, languages: false, filters: false, previews: false,
        retention: 300, incognito: false, sessionOnly: false, paste: false, horizontal: true})
    property string query: ""
    property string typeFilter: "All"
    property bool favoritesOnly: false
    property bool settingsOpen: false
    property int selectedIndex: 0
    property double clockNow: Date.now()
    property var titles: ({})
    property var previewAttempted: ({})
    property var pending: []
    property string copyId: ""
    property bool copyPaste: false
    property string activeScreen: ""
    property int previewGeneration: 0
    property double lastWheelTime: 0
    property real wheelVelocity: 0
    property bool systemMomentum: false
    readonly property var filtered: Model.rows(entries, query, typeFilter, favoritesOnly)
    readonly property var colors: prefs.colors ? Model.palette(entries) : []
    readonly property bool narrow: panel.width < Style.space(720)
    readonly property bool horizontal: prefs.horizontal && !narrow
    readonly property var selectedEntry: selectedIndex >= 0 && selectedIndex < filtered.length ? filtered[selectedIndex] : null

    component CardActionButton: Button {
        focusable: true
        horizontalPadding: Style.space(2)
        color: "transparent"
        borderSpec: Border.none()
        foreground: hot || activeFocus || selected ? Color.accent : Color.menu.text
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Style.space(2)
            width: Math.max(0, parent.width - Style.space(4))
            height: Math.max(1, Style.normalBorderWidth)
            color: Color.accent
            visible: parent.activeFocus
        }
    }

    function open(payload) {
        stopScrolling()
        activeScreen = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : ""
        var screens = Quickshell.screens
        var target = screens.length ? screens[0] : null
        for (var i = 0; i < screens.length; i++) if (screens[i].name === activeScreen) target = screens[i]
        panel.screen = target
        query = ""; search.text = ""; selectedIndex = 0
        clockNow = Date.now()
        opened = true
        Qt.callLater(function() { search.forceActiveFocus() })
    }
    function close() {
        stopScrolling()
        var wasOpened = opened
        opened = false
        previewGeneration++
        confirm.opened = false
        settingsOpen = false
        preview.running = false
        if (wasOpened && shell) shell.hide(pluginId)
    }
    function toggle() { if (opened) close(); else open("") }
    function enqueue(action, argument) {
        if (!integrationEnabled) return
        if (action === "list" && pending.some(function(t) { return t.action === "list" })) return
        pending = pending.concat([{action: action, argument: argument || ""}])
        nextOperation()
    }
    function nextOperation() {
        if (operation.running || !pending.length) return
        var task = pending[0]; pending = pending.slice(1)
        operation.command = ["python3", helper, task.action, stateDir, sessionDir, task.argument]
        operation.running = true
    }
    function applyState(text) {
        try {
            var value = JSON.parse(text)
            if (value.error) { errorText = value.error; return }
            if (!value.settings || !Array.isArray(value.entries)) return
            var selectedId = selectedEntry ? selectedEntry.id : ""
            if (!value.settings.previews) root.previewGeneration++
            prefs = value.settings; entries = value.entries; directory = value.directory
            captureAllowed = value.captureAllowed === true
            ready = true; errorText = captureAllowed ? "" : "Recording disabled: disable omarchy.clipboard before enabling Pano."
            var preserved = filtered.findIndex(function(entry) { return entry.id === selectedId })
            selectedIndex = preserved >= 0 ? preserved : Math.max(0, Math.min(selectedIndex, filtered.length - 1))
            Qt.callLater(function() { if (root.opened) cards.positionViewAtIndex(root.selectedIndex, ListView.Contain) })
            // A result for a removed entry must never reappear after an async request.
            var keep = ({})
            for (var i = 0; i < entries.length; i++) if (titles[entries[i].id]) keep[entries[i].id] = titles[entries[i].id]
            titles = prefs.previews ? keep : ({})
            var attempted = ({})
            for (var j = 0; j < entries.length; j++) if (previewAttempted[entries[j].id]) attempted[entries[j].id] = true
            previewAttempted = prefs.previews ? attempted : ({})
            if (!prefs.previews || !entries.some(function(e) { return e.id === preview.entryId })) preview.running = false
            previewDelay.restart()
        } catch (e) { errorText = "Could not read history; existing files were left untouched." }
    }
    function setting(key, value) {
        var patch = ({}); patch[key] = value
        enqueue("settings", JSON.stringify(patch))
    }
    function select(delta) {
        stopScrolling()
        if (!filtered.length) return
        selectedIndex = (selectedIndex + delta + filtered.length) % filtered.length
        cards.positionViewAtIndex(selectedIndex, ListView.Contain)
    }
    function scrollCards(delta) {
        cards.contentX = Math.max(0, Math.min(Math.max(0, cards.contentWidth - cards.width), cards.contentX + delta))
    }
    function stopScrolling() {
        wheelIdle.stop()
        cards.cancelFlick()
        lastWheelTime = 0
        wheelVelocity = 0
        systemMomentum = false
    }
    function finishScroll() {
        wheelIdle.stop()
        var recent = Date.now() - lastWheelTime <= 120
        var velocity = wheelVelocity
        var coast = !systemMomentum && recent && Math.abs(velocity) >= Style.space(120)
        lastWheelTime = 0
        wheelVelocity = 0
        systemMomentum = false
        if (coast && opened && horizontal && !settingsOpen) cards.flick(velocity, 0)
    }
    function wheelCards(event) {
        event.accepted = true
        if (event.phase === Qt.ScrollBegin) stopScrolling()
        if (event.phase === Qt.ScrollEnd) { finishScroll(); return }
        var pixel = Math.abs(event.pixelDelta.x) >= Math.abs(event.pixelDelta.y) ? event.pixelDelta.x : event.pixelDelta.y
        var angle = Math.abs(event.angleDelta.x) >= Math.abs(event.angleDelta.y) ? event.angleDelta.x : event.angleDelta.y
        var touchpad = pixel !== 0 || event.phase !== Qt.NoScrollPhase || (event.device && event.device.type === PointerDevice.TouchPad)
        if (!touchpad) {
            stopScrolling()
            scrollCards(-angle / 120 * Style.space(160))
            return
        }
        if (event.phase === Qt.ScrollMomentum) systemMomentum = true
        var delta = -(pixel || angle / 120 * Style.space(160)) * 1.7
        if (!delta) return
        cards.cancelFlick()
        scrollCards(delta)
        var now = Date.now()
        var elapsed = lastWheelTime ? now - lastWheelTime : 16
        var velocity = -delta * 1000 / Math.max(8, Math.min(80, elapsed))
        if (lastWheelTime && elapsed < 80 && velocity * wheelVelocity > 0)
            velocity = wheelVelocity * 0.6 + velocity * 0.4
        wheelVelocity = Math.max(-cards.maximumFlickVelocity, Math.min(cards.maximumFlickVelocity, velocity))
        lastWheelTime = now
        // Some Wayland touchpads omit ScrollEnd; idle also releases the gesture.
        wheelIdle.restart()
    }
    function copy(entry, keepOpen) {
        if (!entry || copier.running || copyTimer.running) return
        stopScrolling()
        copyId = entry.id; copyPaste = prefs.paste && !keepOpen
        if (!keepOpen) close()
        copyTimer.restart()
    }
    function key(event) {
        if (confirm.opened) { event.accepted = confirm.handleKey(event); return }
        if (event.key === Qt.Key_Escape) { if (settingsOpen) settingsOpen = false; else close(); event.accepted = true }
        else if (!settingsOpen && (event.key === Qt.Key_Down || event.key === Qt.Key_Right && (!search.activeFocus || !root.query))) { select(1); event.accepted = true }
        else if (!settingsOpen && (event.key === Qt.Key_Up || event.key === Qt.Key_Left && (!search.activeFocus || !root.query))) { select(-1); event.accepted = true }
        else if (!settingsOpen && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && search.activeFocus) { copy(selectedEntry, false); event.accepted = true }
        else if (event.modifiers & Qt.ControlModifier) {
            if (event.key === Qt.Key_F) { settingsOpen = false; search.forceActiveFocus(); event.accepted = true }
            else if (event.key === Qt.Key_S) { settingsOpen = !settingsOpen; event.accepted = true }
            else if (settingsOpen) return
            else if (event.key === Qt.Key_B) { favoritesOnly = !favoritesOnly; event.accepted = true }
            else if (event.key === Qt.Key_P) { if (selectedEntry) enqueue("pin", selectedEntry.id); event.accepted = true }
            else if (event.key === Qt.Key_D) { if (selectedEntry) enqueue("favorite", selectedEntry.id); event.accepted = true }
            else if (event.key >= Qt.Key_1 && event.key <= Qt.Key_8) { typeFilter = Model.types[event.key - Qt.Key_1]; selectedIndex = 0; event.accepted = true }
            else if (event.key === Qt.Key_Delete) { confirm.selectedIndex = 0; confirm.opened = true; event.accepted = true }
        } else if (event.key === Qt.Key_Delete && !settingsOpen && !search.activeFocus) { if (selectedEntry) enqueue("delete", selectedEntry.id); event.accepted = true }
    }
    onQueryChanged: { stopScrolling(); selectedIndex = 0 }
    onTypeFilterChanged: { stopScrolling(); selectedIndex = 0 }
    onFavoritesOnlyChanged: { stopScrolling(); selectedIndex = 0 }
    onFilteredChanged: stopScrolling()
    onHorizontalChanged: stopScrolling()
    onSettingsOpenChanged: {
        stopScrolling()
        Qt.callLater(function() {
            if (!root.opened) return
            if (root.settingsOpen) backToHistory.forceActiveFocus()
            else search.forceActiveFocus()
        })
    }
    onSelectedEntryChanged: previewDelay.restart()
    onOpenedChanged: if (opened) previewDelay.restart()
    Component.onCompleted: if (integrationEnabled) enqueue("init")
    Component.onDestruction: {
        watcher.running = false
        preview.running = false
        if (integrationEnabled) Quickshell.execDetached(["python3", helper, "cleanup-session", stateDir, sessionDir])
    }
    Timer { id: wheelIdle; interval: 80; onTriggered: root.finishScroll() }
    Timer { interval: 30000; running: root.opened; repeat: true; onTriggered: root.clockNow = Date.now() }
    Timer {
        id: copyTimer
        interval: 40
        onTriggered: {
            if (!root.integrationEnabled) return
            copier.command = ["python3", root.helper, "copy", root.stateDir, root.sessionDir, root.copyId, root.copyPaste ? "paste" : "copy"]
            copier.running = true
        }
    }
    Process {
        id: operation
        stdout: StdioCollector { onStreamFinished: root.applyState(text) }
        onExited: function(code) {
            if (code !== 0) root.errorText = "Clipboard operation failed; history was not replaced."
            Qt.callLater(root.nextOperation)
        }
    }
    Process {
        id: copier
        stdout: StdioCollector {
            onStreamFinished: {
                if (text.indexOf('"error"') >= 0) {
                    root.errorText = "Could not copy this entry."
                    if (!root.opened) root.open("")
                }
            }
        }
        onExited: function(code) {
            if (code !== 0) { root.errorText = "Copy or automatic paste failed."; if (!root.opened) root.open("") }
        }
    }
    // The native plugin must be disabled before activation. A file lock also
    // prevents two Pano instances from capturing simultaneously during reload.
    Process {
        id: watcher
        running: root.integrationEnabled && root.ready && root.captureAllowed && !root.prefs.incognito && !restartWatch.running
        command: ["flock", "--nonblock", "--no-fork", root.stateDir + "/watcher.lock", "setpriv", "--pdeathsig", "TERM", "wl-paste", "--watch", "timeout", "8s", "python3", root.helper, "capture", root.stateDir, root.sessionDir]
        stdout: SplitParser { onRead: function(data) { root.enqueue("list") } }
        onExited: {
            if (root.ready && !root.prefs.incognito) {
                root.errorText = "Clipboard watcher stopped; retrying. Check that the built-in clipboard plugin is disabled."
                restartWatch.restart()
            }
        }
    }
    Timer { id: restartWatch; interval: 2000 }
    FileView {
        id: historyWatch
        path: root.ready ? root.directory + "/history.json" : ""
        watchChanges: true
        preload: true
        printErrors: false
        onFileChanged: { reload(); refreshDelay.restart() }
    }
    FileView {
        path: root.integrationEnabled ? (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/omarchy/shell.json" : ""
        watchChanges: true
        preload: true
        printErrors: false
        onFileChanged: { reload(); refreshDelay.restart() }
    }
    Timer { id: refreshDelay; interval: 70; onTriggered: root.enqueue("list") }
    // Settings are stored separately from history so incognito/session mode do
    // not require writing copied contents to the persistent directory.
    FileView {
        path: root.ready ? root.stateDir + "/settings.json" : ""
        watchChanges: true
        preload: true
        printErrors: false
        onFileChanged: { reload(); root.enqueue("list") }
    }
    Timer {
        id: previewDelay
        interval: 180
        onTriggered: {
            var entry = root.selectedEntry
            if (!root.integrationEnabled || !root.opened || !root.prefs.previews || !entry || entry.kind !== "link" || root.previewAttempted[entry.id] || preview.running) return
            var attempted = root.previewAttempted; attempted[entry.id] = true; root.previewAttempted = attempted
            preview.entryId = entry.id
            preview.generation = root.previewGeneration
            preview.command = ["python3", root.helper, "preview", root.stateDir, root.sessionDir, entry.id]
            preview.running = true
            previewTimeout.restart()
        }
    }
    Timer { id: previewTimeout; interval: 4000; onTriggered: preview.running = false }
    Process {
        id: preview
        property string entryId: ""
        property int generation: 0
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    if (preview.generation === root.previewGeneration && root.opened && root.prefs.previews && result.id && result.title && root.entries.some(function(e) { return e.id === result.id })) {
                        var next = Object.assign({}, root.titles); next[result.id] = result.title; root.titles = next
                    }
                } catch (e) {} // A basic link card remains useful on preview failure.
            }
        }
        onExited: { previewTimeout.stop(); previewDelay.restart() }
    }

    PanelWindow {
        id: panel
        visible: root.opened
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "omarchy-clipboard"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: root.opened ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        Rectangle { anchors.fill: parent; color: Color.menu.scrim }
        MouseArea { anchors.fill: parent; onClicked: root.close() }
        BorderSurface {
            id: surface
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.horizontal && !root.settingsOpen ? parent.height - height - Style.gapsOut : (parent.height - height) / 2
            width: root.horizontal && !root.settingsOpen ? panel.width - Style.space(24) : Math.min(Style.space(1080), panel.width - Style.space(24))
            height: Math.min(Style.space(root.horizontal && !root.settingsOpen ? (root.prefs.filters ? 390 : 350) : 620), panel.height - Style.space(24))
            color: Color.menu.background
            radius: Style.cornerRadius
            padding: Style.spacing.panelPadding
            borderSpec: Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))
            MouseArea { anchors.fill: parent; onClicked: {} }
            FocusScope {
                id: content
                anchors.fill: parent
                anchors.margins: Style.spacing.panelPadding
                focus: true
                Keys.priority: Keys.AfterItem
                Keys.onPressed: function(event) { root.key(event) }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Style.spacing.md
                    RowLayout {
                        id: settingsHeader
                        visible: root.settingsOpen
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Settings"
                            color: Color.menu.text
                            font.family: Style.font.menuFamily
                            font.pixelSize: Style.font.heading
                        }
                        Button {
                            id: backToHistory
                            text: "Back"
                            focusable: true
                            Accessible.name: "Back to clipboard"
                            onClicked: root.settingsOpen = false
                        }
                    }
                    GridLayout {
                        id: historyHeader
                        visible: !root.settingsOpen
                        columns: root.narrow ? 1 : 2
                        Layout.fillWidth: true
                        rowSpacing: Style.spacing.sm
                        columnSpacing: Style.spacing.md
                        Flow {
                            id: paletteFlow
                            visible: root.prefs.colors && root.colors.length > 0
                            Layout.fillWidth: root.narrow
                            Layout.preferredWidth: root.narrow ? -1 : Math.min(root.colors.length * Style.space(30), Style.space(300))
                            Layout.minimumWidth: root.narrow ? 0 : Math.min(root.colors.length * Style.space(30), Style.space(300))
                            Layout.minimumHeight: visible ? childrenRect.height : 0
                            Layout.preferredHeight: childrenRect.height
                            spacing: Style.space(4)
                            Repeater {
                                model: root.colors
                                Button {
                                    id: swatch
                                    required property var modelData
                                    width: Style.space(26); height: Style.space(26)
                                    focusable: true
                                    tooltipText: "Copy color " + modelData.preview
                                    Accessible.role: Accessible.Button
                                    Accessible.name: tooltipText
                                    onClicked: root.copy(modelData, true)
                                    Rectangle {
                                        anchors.fill: parent; anchors.margins: Style.space(4)
                                        color: Color.menu.text
                                        Rectangle { width: parent.width / 2; height: parent.height / 2; color: Color.menu.background }
                                        Rectangle { x: parent.width / 2; y: parent.height / 2; width: parent.width / 2; height: parent.height / 2; color: Color.menu.background }
                                        Rectangle { anchors.fill: parent; color: Qt.rgba(swatch.modelData.rgba[0], swatch.modelData.rgba[1], swatch.modelData.rgba[2], swatch.modelData.rgba[3]) }
                                    }
                                }
                            }
                        }
                        TextField {
                            id: search
                            Layout.fillWidth: true
                            placeholderText: "Search clipboard…"
                            Accessible.name: "Search clipboard"
                            onTextChanged: root.query = text
                            Keys.priority: Keys.BeforeItem
                            Keys.onPressed: function(event) { root.key(event) }
                        }
                    }
                    Flow {
                        id: filterFlow
                        Layout.fillWidth: true
                        Layout.preferredHeight: childrenRect.height
                        visible: !root.settingsOpen && root.prefs.filters
                        spacing: Style.space(3)
                        Repeater {
                            model: Model.types
                            Button {
                                required property string modelData
                                required property int index
                                text: modelData
                                focusable: true
                                selected: root.typeFilter === modelData
                                fontSize: Style.font.caption
                                horizontalPadding: Style.space(8)
                                Accessible.role: Accessible.Button
                                Accessible.name: "Filter " + modelData + ", Control " + (index + 1)
                                Accessible.checkable: true
                                Accessible.checked: selected
                                onClicked: root.typeFilter = modelData
                            }
                        }
                    }
                    Flow {
                        id: historyActions
                        visible: !root.settingsOpen
                        Layout.fillWidth: true
                        Layout.preferredHeight: childrenRect.height
                        spacing: Style.space(3)
                        Button { text: "Favorites"; selected: root.favoritesOnly; focusable: true; onClicked: root.favoritesOnly = !root.favoritesOnly; Accessible.name: "Show favorites" }
                        Button { text: root.prefs.incognito ? "Recording paused" : "Recording"; selected: root.prefs.incognito; focusable: true; onClicked: root.setting("incognito", !root.prefs.incognito); Accessible.name: "Toggle incognito" }
                        Button { text: "Settings"; selected: root.settingsOpen; focusable: true; onClicked: root.settingsOpen = !root.settingsOpen }
                        Button { text: "Clear…"; focusable: true; onClicked: { confirm.selectedIndex = 0; confirm.opened = true } }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: root.errorText || (!root.ready ? "Loading clipboard history…" : root.prefs.sessionOnly ? "Session only · discarded when plugin unloads" : "")
                        color: root.errorText ? Color.urgent : Color.menu.text
                        font.family: Style.font.menuFamily; font.pixelSize: Style.font.caption
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                    }
                    Flickable {
                        id: settingsView
                        visible: root.settingsOpen
                        Layout.fillWidth: true; Layout.fillHeight: true
                        contentHeight: settingsColumn.height
                        clip: true
                        Column {
                            id: settingsColumn
                            width: parent.width
                            spacing: Style.spacing.sm
                            Repeater {
                                model: [
                                    {key: "incognito", label: "Incognito (pause recording)"},
                                    {key: "colors", label: "Recent-color palette"},
                                    {key: "languages", label: "Code-language tags"},
                                    {key: "filters", label: "Quick type-filter buttons"},
                                    {key: "previews", label: "Download link titles (contacts copied sites)"},
                                    {key: "sessionOnly", label: "Session-only history"},
                                    {key: "paste", label: "Automatically paste after selection"},
                                    {key: "horizontal", label: "Horizontal cards on wide screens"}
                                ]
                                Toggle {
                                    required property var modelData
                                    width: parent.width
                                    label: modelData.label
                                    checked: !!root.prefs[modelData.key]
                                    Accessible.name: label
                                    onClicked: root.setting(modelData.key, !checked)
                                }
                            }
                            NumberField {
                                label: "History limit"
                                value: root.prefs.retention
                                from: 0; to: 5000
                                onModified: function(value) { root.setting("retention", value) }
                            }
                            Text {
                                width: parent.width
                                text: "Shortcut: configure Hyprland to run omarchy-shell shell toggle sterling.pano.\nCtrl+1…8: type · Ctrl+B: favorites · Ctrl+D: favorite · Ctrl+P: pin · Ctrl+F: search · Ctrl+S: settings · Ctrl+Delete: clear"
                                wrapMode: Text.Wrap; color: Color.menu.text
                                textFormat: Text.PlainText
                                font.family: Style.font.menuFamily; font.pixelSize: Style.font.caption
                            }
                        }
                    }
                    ListView {
                        id: cards
                        visible: !root.settingsOpen
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true
                        model: root.filtered
                        orientation: root.horizontal ? ListView.Horizontal : ListView.Vertical
                        spacing: Style.spacing.md
                        boundsBehavior: Flickable.StopAtBounds
                        cacheBuffer: 0
                        maximumFlickVelocity: Style.space(2400)
                        flickDeceleration: Style.space(5200)
                        onDraggingChanged: if (dragging) root.stopScrolling()
                        currentIndex: root.selectedIndex
                        MouseArea {
                            parent: cards
                            anchors.fill: parent
                            z: 1
                            enabled: root.horizontal
                            acceptedButtons: Qt.NoButton
                            onWheel: function(event) { root.wheelCards(event) }
                        }
                        delegate: BorderSurface {
                            id: card
                            required property var modelData
                            required property int index
                            readonly property bool selected: index === root.selectedIndex
                            width: root.horizontal ? Math.min(cards.width, Style.space(220)) : cards.width
                            height: root.horizontal ? Math.min(cards.height, Style.space(230)) : Style.space(180)
                            color: selected ? Color.menu.selectedBackground : Style.normalFillFor(Color.menu.text, Color.accent)
                            borderSpec: Border.controlSpec(activeFocus ? "focus" : selected || hover.hovered ? "hover-cursor" : "normal", Color.menu.text, Color.accent)
                            radius: Style.cornerRadius
                            activeFocusOnTab: true
                            onActiveFocusChanged: if (activeFocus) { root.stopScrolling(); root.selectedIndex = index }
                            Accessible.role: Accessible.Button
                            Accessible.name: modelData.kind + ": " + modelData.preview.slice(0, 160)
                            Accessible.onPressAction: root.copy(modelData, false)
                            Keys.onReturnPressed: root.copy(modelData, false)
                            Keys.onSpacePressed: root.copy(modelData, false)
                            Keys.priority: Keys.BeforeItem
                            Keys.onPressed: function(event) { if (event.modifiers & Qt.ControlModifier || event.key === Qt.Key_Escape) root.key(event) }
                            HoverHandler { id: hover }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: { root.selectedIndex = card.index; root.copy(card.modelData, false) }
                            }
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: card.borderTop
                                spacing: 0
                                BorderSurface {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Style.space(54)
                                    color: Style.selectedFillFor(Color.menu.text, Color.accent)
                                    radius: Style.cornerRadius
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: Style.spacing.sm
                                        spacing: Style.spacing.sm
                                        Text {
                                            text: Model.typeIcon(card.modelData.kind)
                                            color: Color.accent
                                            font.family: Style.font.family
                                            font.pixelSize: Style.space(24)
                                            textFormat: Text.PlainText
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 0
                                            Text {
                                                Layout.fillWidth: true
                                                text: card.modelData.kind.charAt(0).toUpperCase() + card.modelData.kind.slice(1)
                                                color: Color.menu.text
                                                font.family: Style.font.menuFamily; font.pixelSize: Style.font.subtitle
                                                elide: Text.ElideRight; textFormat: Text.PlainText
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: Model.age(card.modelData.copiedAt || 0, root.clockNow)
                                                color: Color.menu.text; opacity: 0.65
                                                font.family: Style.font.menuFamily; font.pixelSize: Style.font.caption
                                                elide: Text.ElideRight
                                            }
                                            Text {
                                                visible: root.prefs.languages && card.modelData.kind === "code"
                                                Layout.fillWidth: true
                                                text: card.modelData.language || "Code"
                                                color: Color.accent
                                                font.family: Style.font.menuFamily; font.pixelSize: Style.font.caption
                                                elide: Text.ElideRight; textFormat: Text.PlainText
                                            }
                                        }
                                        CardActionButton {
                                            text: selected ? "󰐃" : "󰤱"
                                            selected: !!card.modelData.pinnedAt
                                            tooltipText: selected ? "Unpin card" : "Pin card to front"
                                            Accessible.name: tooltipText
                                            Accessible.role: Accessible.Button
                                            Accessible.checkable: true
                                            Accessible.checked: selected
                                            onClicked: root.enqueue("pin", card.modelData.id)
                                        }
                                        CardActionButton { text: card.modelData.favorite ? "★" : "☆"; Accessible.name: card.modelData.favorite ? "Unfavorite entry" : "Favorite entry"; onClicked: root.enqueue("favorite", card.modelData.id) }
                                        CardActionButton { text: "×"; Accessible.name: "Delete entry"; onClicked: root.enqueue("delete", card.modelData.id) }
                                    }
                                }
                                Item {
                                    Layout.fillWidth: true; Layout.fillHeight: true
                                    Layout.margins: Style.spacing.md
                                    clip: true
                                    Text {
                                        anchors.fill: parent
                                        visible: card.modelData.kind !== "image" || imagePreview.status === Image.Error
                                        text: card.modelData.kind === "image" ? "Image preview unavailable · " + card.modelData.preview : root.titles[card.modelData.id] ? root.titles[card.modelData.id] + "\n" + card.modelData.preview : card.modelData.preview
                                        textFormat: Text.PlainText
                                        color: Color.menu.text
                                        font.family: Style.font.menuFamily; font.pixelSize: Style.font.body
                                        wrapMode: Text.WrapAnywhere; elide: Text.ElideRight
                                    }
                                    Image {
                                        id: imagePreview
                                        anchors.fill: parent
                                        visible: card.modelData.kind === "image"
                                        source: visible ? Util.fileUrl(root.directory + "/" + card.modelData.id) : ""
                                        sourceSize.width: Style.space(480); sourceSize.height: Style.space(300)
                                        fillMode: Image.PreserveAspectFit; asynchronous: true
                                    }
                                    Rectangle {
                                        visible: card.modelData.kind === "color" && card.modelData.rgba && card.modelData.rgba.length === 4
                                        anchors.right: parent.right; anchors.bottom: parent.bottom
                                        width: Style.space(50); height: Style.space(30)
                                        color: Color.menu.text
                                        Rectangle { width: parent.width / 2; height: parent.height / 2; color: Color.menu.background }
                                        Rectangle { x: parent.width / 2; y: parent.height / 2; width: parent.width / 2; height: parent.height / 2; color: Color.menu.background }
                                        Rectangle { anchors.fill: parent; color: parent.visible ? Qt.rgba(card.modelData.rgba[0], card.modelData.rgba[1], card.modelData.rgba[2], card.modelData.rgba[3]) : "transparent" }
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        visible: !root.settingsOpen && root.ready && root.filtered.length === 0
                        Layout.fillWidth: true
                        text: root.entries.length ? "No entries match these filters." : "Clipboard is empty. Copy something to begin."
                        color: Color.menu.text; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body
                        wrapMode: Text.Wrap; textFormat: Text.PlainText
                    }
                }
                ConfirmDialog {
                    id: confirm
                    anchors.fill: parent
                    z: 50
                    message: "Delete all history, including saved history, pinned cards and favorites?"
                    confirmText: "Delete"
                    Keys.priority: Keys.BeforeItem
                    Keys.onPressed: function(event) { root.key(event) }
                    onOpenedChanged: if (opened) forceActiveFocus()
                    onCanceled: { opened = false; search.forceActiveFocus() }
                    onConfirmed: { opened = false; root.previewGeneration++; root.titles = ({}); root.previewAttempted = ({}); preview.running = false; root.enqueue("clear"); search.forceActiveFocus() }
                }
            }
        }
    }
}
