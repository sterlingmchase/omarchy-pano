#!/usr/bin/env python3
"""Dispatch Qt wheel events through Pano's actual input surface, offscreen."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'Pano.qml').read_text()
# Use the shipped receiver unchanged; other card rendering is irrelevant here.
receiver = source.split('currentIndex: root.selectedIndex', 1)[1].split('delegate: BorderSurface', 1)[0]
with tempfile.TemporaryDirectory(prefix='pano-wheel-') as tmp:
    stage = Path(tmp)
    (stage / 'tst_wheel.qml').write_text('''import QtQuick
import QtTest
Item {
    id: root
    width: 800; height: 400
    property bool horizontal: true
    property int calls: 0
    property int clicks: 0
    function wheelCards(event) { calls++; event.accepted = true }
    ListView {
        id: cards
        anchors.fill: parent
        orientation: root.horizontal ? ListView.Horizontal : ListView.Vertical
        model: 20
        ''' + receiver + '''
        delegate: Rectangle {
            width: 220; height: 200
            MouseArea { anchors.fill: parent; onClicked: root.clicks++ }
        }
    }
    TestCase {
        name: "PanoWheelDelivery"
        when: windowShown
        function test_wheel_data() {
            return [{tag: "vertical", x: 0, y: -120},
                    {tag: "horizontal", x: -120, y: 0},
                    {tag: "diagonal", x: -120, y: -120}]
        }
        function test_wheel(data) {
            root.calls = 0
            mouseWheel(cards, 100, 100, data.x, data.y)
            compare(root.calls, 1, "Each wheel event must be handled exactly once")
        }
        function test_clickThrough() {
            mouseClick(cards, 100, 100)
            compare(root.clicks, 1, "Wheel receiver must not intercept card clicks")
        }
        function test_scrolledViewport() {
            cards.contentX = 300
            root.calls = 0
            mouseWheel(cards, 100, 300, -120, -120)
            compare(root.calls, 1, "Receiver must cover the viewport after scrolling")
            cards.contentX = 0
        }
        function test_narrow() {
            root.horizontal = false
            root.calls = 0
            mouseWheel(cards, 100, 100, 0, -120)
            compare(root.calls, 0, "Narrow layout keeps native wheel scrolling")
            tryVerify(function() { return cards.contentY > 0 })
            cards.cancelFlick()
            cards.contentY = 0
            root.horizontal = true
        }
    }
}''')
    runtime = stage / 'runtime'
    runtime.mkdir(mode=0o700)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM='offscreen',
               QT_QPA_PLATFORMTHEME='generic', QT_QUICK_BACKEND='software')
    subprocess.run(['/usr/lib/qt6/bin/qmltestrunner', '-input', str(stage)], env=env,
                   check=True, timeout=15)
