# Anki Deadline2
# Anki 2.1 plugin
# Author: BSC
# Version 2_5
# Description: Adjusts 'New Cards per Day' setting of options group to ensure all cards
#              are seen by deadline.
# License: GNU GPL v3 <www.gnu.org/licenses/gpl.html>

import datetime
import math
import time

from anki.hooks import addHook, wrap
from anki.utils import intTime
from aqt import *
from aqt.main import AnkiQt
from aqt.qt import *
from aqt.utils import (askUser, getOnlyText, openHelp, openLink, showInfo,
                       showWarning)

from . import CalForm, ConfigForm


class DeadlineDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self, parent=mw)  # , Qt.Window)

        self.mw = aqt.mw
        self.deadlines = mw.addonManager.getConfig(__name__)
        self.deadlines.pop("test")
        self.form = ConfigForm.Ui_Dialog()
        self.form.setupUi(self)
        self.setWindowTitle(_("Deadline"))
        self.form.ProcessDeadlineBox.clicked.connect(self.callDeadlines)
        self.fillFields()
        self.setupSignals()
        if self.deadlines.get("oneOrMany", "") == "Many":
            self.form.OneOrManyBox.setCurrentIndex(1)
        else:
            self.form.OneOrManyBox.setCurrentIndex(0)
        self.resize(500, 500)
        self.Calwindow = QDialog(self)
        self.LayoutForCal = CalForm.Ui_Dialog()
        self.LayoutForCal.setupUi(self.Calwindow)
        self.LayoutForCal.pushButton.clicked.connect(self.readValues)
        self.exec()

    def callDeadlines(self):
        from . import manualDeadlines

        tempString = str(self.form.OneOrManyBox.currentText())
        if tempString.find("Single") != -1:
            self.deadlines["oneOrMany"] = "One"
        else:
            self.deadlines["oneOrMany"] = "Many"
        mw.addonManager.writeConfig(__name__, self.deadlines)
        manualDeadlines()

    def fillFields(self):
        self.form.fieldList.clear()
        for user in self.deadlines["deadlines"]:
            if user != str(aqt.mw.pm.name):
                continue
            for deck, deadline in self.deadlines["deadlines"].get(user).items():
                if deadline == "":
                    continue
                self.form.fieldList.addItem(
                    "user:{{{}}} deck:{{{}}} date:{{{}}}".format(user, deck, deadline)
                )

    def setupSignals(self):
        f = self.form
        f.AddDeadlineButton.clicked.connect(self.onAdd)
        f.DeleteDeadlineButton.clicked.connect(self.onDelete)
        f.buttonBox.helpRequested.connect(self.onHelp)

    def readValues(self):
        if self.LayoutForCal.checkBox_2.isChecked():
            if not utils.askUser(
                "Are you sure you want to continue? The Apply to all Sub-Decks Box is checked"
            ):
                return
        user = str(aqt.mw.pm.name)
        year = self.LayoutForCal.calendarWidget.selectedDate().year()
        month = self.LayoutForCal.calendarWidget.selectedDate().month()
        day = self.LayoutForCal.calendarWidget.selectedDate().day()
        date = "{}-{}-{}".format(year, str(month).zfill(2), str(day).zfill(2))
        self.Calwindow.close()
        if not user in self.deadlines["deadlines"]:
            self.deadlines["deadlines"][user] = {}
        tempString = str(self.form.OneOrManyBox.currentText())
        if tempString.find("Single") != -1:
            self.deadlines["oneOrMany"] = "One"
        else:
            self.deadlines["oneOrMany"] = "Many"
        while self.LayoutForCal.listWidget.selectedIndexes():
            deck = self.LayoutForCal.listWidget.item(
                self.LayoutForCal.listWidget.selectedIndexes()[0].row()
            ).text()
            self.LayoutForCal.listWidget.takeItem(
                self.LayoutForCal.listWidget.selectedIndexes()[0].row()
            )
            self.applyDeadlineForDeck(deck, date)
        self.fillFields()

    def applyDeadlineForDeck(self, deck, date):
        user = str(aqt.mw.pm.name)

        childIds = list(mw.col.decks.child_ids(deck))
        if childIds and not self.LayoutForCal.checkBox_2.isChecked():
            return
        elif childIds and self.LayoutForCal.checkBox_2.isChecked():
            for child in childIds:
                childName = mw.col.decks.name(child)
                self.applyDeadlineForDeck(childName, date)
            return

        # Get the deck ID
        DeckIDToUpdate = mw.col.decks.id_for_name(deck)

        # Add the deadline to the config
        self.deadlines["deadlines"][user][deck] = date

        # Get the current deck config
        deck_obj = mw.col.decks.get(DeckIDToUpdate)
        current_config_id = deck_obj.get("conf_id", 1)  # default to 1 if not found

        # Only create a new config if using the default
        if current_config_id == 1:
            # Get the current config dict
            current_config = mw.col.decks.get_config(current_config_id)
            # Create new config based on current settings
            new_config_id = mw.col.decks.add_config_returning_id(deck, current_config)
            # Update the deck to use the new config
            deck_obj["conf_id"] = new_config_id
            mw.col.decks.save(deck_obj)

        # Save the deadlines config
        mw.addonManager.writeConfig(__name__, self.deadlines)

    def onAdd(self):
        self.Calwindow.show()
        self.LayoutForCal.listWidget.clear()
        for deck in sorted(aqt.mw.col.decks.all_names()):
            self.LayoutForCal.listWidget.addItem(deck)

    def onDelete(self):
        while self.form.fieldList.selectedIndexes():
            temp = self.form.fieldList.item(
                self.form.fieldList.selectedIndexes()[0].row()
            ).text()
            self.form.fieldList.takeItem(self.form.fieldList.selectedIndexes()[0].row())
            fields = temp.split("}")
            user = fields[0].split("{")[1]
            deck = fields[1].split("{")[1]
            date = fields[2].split("{")[1]
            self.deadlines["deadlines"].get(user).pop(deck)
            mw.addonManager.writeConfig(__name__, self.deadlines)
            delConfId = mw.col.decks.by_name(deck)["conf"]
            # Don't even attempt to delete the default conf; otherwise we would get an error pop up
            if delConfId != 1:
                mw.col.decks.remove_config(delConfId)
        # self.fillFields()

    def onHelp(self):
        openLink("https://github.com/BSCrumpton/Deadline2")
