import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1180; height: 820; minimumWidth: 860; minimumHeight: 620
    visible: true; title: "CrossGen-AGI-μ"
    color: win.canvas
    font.family: "Microsoft JhengHei UI"
    font.pixelSize: 14
    property bool dark: crossgen.darkMode
    property color ink: dark ? "#eff0fc" : "#172445"
    property color muted: dark ? "#b2b9d2" : "#5e6b85"
    property color accent: dark ? "#bdadff" : "#6050b5"
    property color canvas: dark ? "#141929" : "#f6f6fe"
    property color panel: dark ? "#1a2035" : "#edf4ff"
    property color card: dark ? "#20263c" : "#ffffff"
    property color line: dark ? "#39415e" : "#dce1f0"
    property color soft: dark ? "#282e49" : "#f0effb"
    property color selected: dark ? "#39395c" : "#e6e9fb"
    property color hoverColor: dark ? "#353c59" : "#e5eafd"
    property color badgeBg: dark ? "#343147" : "#f0eafa"
    property color badgeInk: dark ? "#c9bddf" : "#706080"
    property color onAccent: dark ? "#172445" : "#172445"
    property color accentHover: dark ? "#cdbdff" : "#b9cdf7"
    palette.window: canvas
    palette.windowText: ink
    palette.base: card
    palette.text: ink
    palette.button: soft
    palette.buttonText: ink
    palette.highlight: accent
    palette.highlightedText: onAccent
    background: Rectangle {
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: win.dark ? "#151e32" : "#edf8ff" }
            GradientStop { position: 0.55; color: win.dark ? "#201c34" : "#f5efff" }
            GradientStop { position: 1; color: win.dark ? "#2b2030" : "#fff2ec" }
        }
    }
    property bool compact: width < 1040
    function stateText(state) {
        return ({idle:"準備開始",queued:"準備執行",running:"正在處理",cancelling:"正在停止",completed:"已完成",partial:"部分完成",failed:"未完成",blocked:"需要處理",cancelled:"已取消",interrupted:"上次已中斷"})[state] || state
    }
    component QuietButton: Button {
        id: qb
        implicitHeight: 38
        horizontalPadding: 16
        background: Rectangle { color: qb.down ? win.hoverColor : qb.hovered ? win.hoverColor : "transparent"; radius: 9; border.width: qb.activeFocus ? 2 : 0; border.color: win.accent }
        contentItem: Text { text: qb.text; color: qb.enabled ? win.ink : win.muted; font: qb.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
    }
    component BrandButtonSurface: Rectangle {
        property bool hovered: false
        radius: 10
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: hovered ? "#b4d9f8" : "#c8e7fc" }
            GradientStop { position: 0.52; color: hovered ? "#cec0f1" : "#e0d4fa" }
            GradientStop { position: 1; color: hovered ? "#f5c4d3" : "#fadddf" }
        }
        border.color: win.dark ? "#a49ed5" : "#d0d8f2"
    }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: win.compact ? 218 : 248; Layout.fillHeight: true; color: win.panel
            gradient: Gradient {
                GradientStop { position: 0; color: win.dark ? "#19263a" : "#e8f4ff" }
                GradientStop { position: 0.6; color: win.dark ? "#24223a" : "#eeedfc" }
                GradientStop { position: 1; color: win.dark ? "#30243a" : "#fbeef4" }
            }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 22; spacing: 24
                RowLayout {
                    spacing: 11; Layout.topMargin: 10
                    Rectangle { width: 48; height: 42; radius: 10; color: "white"; border.color: "#dce1f0"
                        Image { objectName: "companyLogo"; anchors.fill: parent; anchors.margins: 4; source: "assets/company-mark.png"; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true }
                    }
                    Column { spacing: 1
                        Text { text: "CrossGen"; font.family: "Segoe UI"; font.pixelSize: 22; font.weight: Font.DemiBold; color: win.ink }
                        Text { text: "AGI–μ  /  工作助理"; font.pixelSize: 11; color: win.muted }
                    }
                }
                Button {
                    id: newButton; text: "+  新任務"; Layout.fillWidth: true; implicitHeight: 43; enabled: !crossgen.busy
                    background: BrandButtonSurface { hovered: newButton.hovered }
                    contentItem: Text { text: newButton.text; color: win.onAccent; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: { crossgen.newTask(); composer.clear(); composer.forceActiveFocus() }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 9
                    Text { text: "工作區"; color: win.muted; font.pixelSize: 11; font.weight: Font.DemiBold; leftPadding: 10 }
                    Rectangle { Layout.fillWidth: true; height: 42; radius: 9; color: win.selected
                        Row { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 12; spacing: 12
                            Item { width: 16; height: 16; anchors.verticalCenter: parent.verticalCenter
                                Repeater { model: 4; delegate: Rectangle { required property int index; x: (index%2)*8; y: Math.floor(index/2)*8; width: 5; height: 5; radius: 1; color: win.accent } }
                            }
                            Text { text: "任務總覽"; color: win.ink; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        Text { text: "最近任務"; color: win.muted; font.pixelSize: 11; leftPadding: 10; Layout.fillWidth: true }
                        Text { text: crossgen.tasks.length; color: win.muted; font.pixelSize: 11; rightPadding: 8 }
                    }
                    ListView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 5; reuseItems: true
                        model: crossgen.tasks
                        delegate: ItemDelegate {
                            required property var modelData
                            width: ListView.view.width; height: 65
                            enabled: !crossgen.busy
                            background: Rectangle { radius: 8; color: parent.hovered ? win.hoverColor : "transparent" }
                            contentItem: Column { spacing: 5
                                Text { text: modelData.prompt; width: parent.width; elide: Text.ElideRight; color: win.ink; font.pixelSize: 12 }
                                Text { text: win.stateText(modelData.status); color: win.muted; font.pixelSize: 11 }
                            }
                            onClicked: crossgen.selectTask(modelData.id)
                        }
                        Text { visible: crossgen.tasks.length===0; text: "完成的工作會留在這裡。"; color: win.muted; font.pixelSize: 11; anchors.left: parent.left; anchors.leftMargin: 10; anchors.top: parent.top; anchors.topMargin: 12 }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: win.line }
                Column { spacing: 7; Layout.fillWidth: true
                    Text { text: "跨世代媒體科技股份有限公司"; color: win.muted; font.pixelSize: 11 }
                    Text { text: "TAIWAN  ·  CrossGen-AGI-μ"; color: win.muted; font.family: "Segoe UI"; font.pixelSize: 11 }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 36; Layout.rightMargin: 36; Layout.topMargin: 26; Layout.bottomMargin: 20
                Text { text: "任務工作區"; color: win.ink; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true }
                QuietButton { text: win.dark ? "淺色" : "深色"; implicitHeight: 30; font.pixelSize: 11; onClicked: crossgen.toggleTheme() }
                Rectangle { implicitWidth: badge.width+22; height: 27; radius: 13; color: win.badgeBg
                    Text { id: badge; anchors.centerIn: parent; text: "開發版本 · 尚未通過發布驗收"; color: win.badgeInk; font.pixelSize: 11 }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: win.line }
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: win.width-(win.compact?218:248)-72
                    x: 36; spacing: 22
                    Item { height: crossgen.detail ? 8 : 26; Layout.fillWidth: true }
                    ColumnLayout {
                        visible: !crossgen.detail; Layout.fillWidth: true; spacing: 15
                        Text { text: "把想做的事，寫在這裡。"; color: win.ink; font.pixelSize: win.compact ? 28 : 34; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Text { text: "描述你想完成的工作。\n操作進度、等待原因與實際結果，都能在這裡查看。"; color: win.muted; font.pixelSize: 14; lineHeight: 1.65; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                    Rectangle {
                        visible: !crossgen.detail; Layout.fillWidth: true; implicitHeight: 120; radius: 15; color: win.card; border.color: win.line
                        RowLayout { anchors.fill: parent; anchors.margins: 22; spacing: 18
                            Rectangle { width: 46; height: 46; radius: 14; color: win.soft
                                Text { anchors.centerIn: parent; text: "↗"; color: win.accent; font.pixelSize: 27 }
                            }
                            ColumnLayout { Layout.fillWidth: true; spacing: 9
                                Text { text: "從一件具體的小事開始"; color: win.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                                Text { text: "檔案、網站、文字或程式，先說明要得到的結果。"; color: win.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                        }
                    }
                    Flow {
                        visible: !crossgen.detail; Layout.fillWidth: true; spacing: 9
                        Repeater {
                            model: ["列出資料夾內容", "整理一段文字", "檢查一段程式"]
                            delegate: QuietButton { required property string modelData; text: modelData; onClicked: { composer.text=modelData;composer.forceActiveFocus() } background: Rectangle { color: parent.hovered ? win.hoverColor : win.soft; radius: 9; border.color: win.line } }
                        }
                    }
                    ColumnLayout {
                        visible: !!crossgen.detail; Layout.fillWidth: true; spacing: 18
                        Text { text: "這次的工作"; color: win.muted; font.pixelSize: 12 }
                        Text { text: crossgen.detail; color: win.ink; font.pixelSize: 22; Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Rectangle { Layout.fillWidth: true; implicitHeight: stateRow.implicitHeight+32; radius: 12; color: win.soft
                            RowLayout { id: stateRow; anchors.fill: parent; anchors.margins: 16; spacing: 12
                                BusyIndicator { running: crossgen.busy; visible: running; implicitWidth: 26; implicitHeight: 26 }
                                Text { text: win.stateText(crossgen.state); color: win.accent; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                QuietButton { text: "停止"; visible: crossgen.busy; onClicked: crossgen.cancel() }
                            }
                        }
                        Repeater {
                            model: crossgen.steps
                            delegate: Rectangle {
                                id: stepCard
                                objectName: "stepCard-"+index
                                required property var modelData
                                required property int index
                                property bool expanded: false
                                Layout.fillWidth: true; implicitHeight: progressColumn.implicitHeight+28; radius: 10; color: win.soft
                                ColumnLayout { id: progressColumn; anchors.fill: parent; anchors.margins: 14; spacing: 7
                                    RowLayout { Layout.fillWidth: true
                                        Text { text: modelData.label; color: win.muted; font.pixelSize: 11; Layout.fillWidth: true }
                                        Text { text: modelData.status; color: win.accent; font.pixelSize: 11 }
                                    }
                                    Text { visible: !stepCard.expanded; text: modelData.detail; color: win.ink; font.pixelSize: 12; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText; Layout.fillWidth: true }
                                    QuietButton { objectName: "stepToggle-"+stepCard.index; text: stepCard.expanded ? "收合回應" : modelData.full ? "展開完整回應" : "展開摘要"; implicitHeight: 28; font.pixelSize: 11; onClicked: stepCard.expanded=!stepCard.expanded }
                                    Loader {
                                        Layout.fillWidth: true; active: stepCard.expanded; visible: active
                                        Layout.preferredHeight: active && item ? item.implicitHeight : 0
                                        sourceComponent: TextArea { objectName: "stepFull-"+stepCard.index; text: modelData.detail; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: win.ink; font.pixelSize: 12; background: null; padding: 0 }
                                    }
                                }
                            }
                        }
                        TextArea { visible: !!crossgen.result; Layout.fillWidth: true; text: crossgen.result; textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: win.ink; font.pixelSize: 14; background: Rectangle { color: win.card; radius: 12; border.color: win.line } padding: 20 }
                        QuietButton { visible: !!crossgen.result; text: "複製結果"; onClicked: crossgen.copyResult() }
                    }
                    Item { Layout.fillWidth: true; height: 20 }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; Layout.margins: 28; Layout.topMargin: 12; spacing: 10
                Rectangle {
                    Layout.fillWidth: true; implicitHeight: 148; radius: 16; color: win.card; border.color: composer.activeFocus ? win.accent : win.line; border.width: 1
                    ColumnLayout { anchors.fill: parent; anchors.margins: 14; spacing: 4
                        ScrollView {
                            id: composerViewport; objectName: "composerViewport"
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            TextArea { id: composer; objectName: "composer"; placeholderText: "告訴 CrossGen，你想完成什麼…"; placeholderTextColor: win.muted; enabled: !crossgen.busy; wrapMode: TextEdit.Wrap; color: win.ink; font.pixelSize: 14; background: null; padding: 3; selectByMouse: true
                                Keys.onPressed: function(event) { if ((event.key===Qt.Key_Return || event.key===Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) { crossgen.submit(text); event.accepted=true } }
                            }
                        }
                        RowLayout { Layout.fillWidth: true
                            QuietButton { objectName: "voiceButton"; text: crossgen.voiceState==="recording" ? "停止錄音" : "語音輸入"; enabled: !crossgen.busy || crossgen.voiceState==="recording"; implicitHeight: 33; onClicked: crossgen.voiceState==="recording" ? crossgen.stopVoice() : crossgen.startVoice() }
                            QuietButton { text: "取消語音"; visible: ["preparing","recording","transcribing","cancelling"].indexOf(crossgen.voiceState)>=0; enabled: crossgen.voiceState!=="cancelling"; onClicked: crossgen.cancelVoice() }
                            Text { text: "繁體中文 · 台灣"; color: win.muted; font.pixelSize: 11; Layout.fillWidth: true }
                            Text { text: "Ctrl + Enter"; color: win.muted; font.family: "Segoe UI"; font.pixelSize: 11; Layout.rightMargin: 8 }
                            Button { id: send; text: "開始處理  ↗"; enabled: !crossgen.busy && composer.text.trim().length>0; implicitWidth: 117; implicitHeight: 37; onClicked: crossgen.submit(composer.text)
                                background: BrandButtonSurface { hovered: send.hovered; opacity: send.enabled ? 1 : 0.5 }
                                contentItem: Text { text: send.text; color: send.enabled ? win.onAccent : win.muted; font.pixelSize: 12; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            }
                        }
                    }
                }
                Text { text: crossgen.voiceMessage; visible: !!text; color: win.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                Text { text: crossgen.development ? "開發模式：執行中的操作會逐步記錄；你可以隨時停止後續步驟。" : "目前仍在驗收階段，自動操作尚未開放。"; color: win.muted; font.pixelSize: 11; Layout.alignment: Qt.AlignHCenter }
            }
        }
    }
    Dialog {
        id: question; anchors.centerIn: parent; width: Math.min(560,win.width-60); height: Math.min(430,win.height-80); modal: true; closePolicy: Popup.NoAutoClose
        property bool confirmation: false
        property string token: ""
        property string message: ""
        contentItem: ColumnLayout { spacing: 15
            ScrollView { Layout.fillWidth: true; Layout.fillHeight: true
                TextArea { text: question.message; wrapMode: TextEdit.Wrap; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText }
            }
            TextField { id: response; visible: !question.confirmation; Layout.fillWidth: true; placeholderText: "輸入回覆" }
            RowLayout { Layout.alignment: Qt.AlignRight
                Button { text: "取消"; onClicked: crossgen.answer(question.token,"") }
                Button { text: question.confirmation ? "確認執行" : "送出回覆"; onClicked: crossgen.answer(question.token,question.confirmation ? "yes" : response.text) }
            }
        }
    }
    Connections {
        target: crossgen
        function onVoiceTextReady(text) { composer.insert(composer.cursorPosition,text);composer.forceActiveFocus() }
        function onDialogRequested(token,title,message,confirm) { question.token=token;question.title=title;question.message=message;question.confirmation=confirm;response.text="";question.open() }
        function onDialogClosed() { question.close() }
    }
}
