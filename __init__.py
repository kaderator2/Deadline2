# Anki Deadline2
# Anki 2.1 plugin
# OriginalAuthor: EJS
# UpdatedAuthor: BSC
# Version 2_5
# Description: Adjusts 'New Cards per Day' setting of options group to ensure all cards
#              are seen by deadline.
# License: GNU GPL v3 <www.gnu.org/licenses/gpl.html>

from __future__ import division

import datetime
import math
import time

from anki.hooks import addHook, wrap
from anki.utils import intTime
from aqt import *
from aqt.main import AnkiQt
from aqt.utils import (askUser, getOnlyText, openHelp, openLink, showInfo,
                       showWarning)

from .config import DeadlineDialog

deadlines = mw.addonManager.getConfig(__name__)

mw.addonManager.setConfigAction(__name__, DeadlineDialog)

DeadlineMenu = QMenu("Deadline", mw)
mw.form.menuTools.addMenu(DeadlineMenu)


# Count new cards in a deck
def new_cards_in_deck(deck_id):
    return mw.col.db.scalar(
        """
        SELECT count() FROM cards 
        WHERE type = 0 
        AND queue != -1 
        AND did = ?
        AND queue != -2""",
        deck_id,
    )  # Exclude suspended cards


# Find settings group ID
def find_settings_group_id(name):
    dconf = mw.col.decks.all_config()
    for k in dconf:
        if k["name"] == name:
            return k["id"]
            # All I want is the group ID
    return False


# Find decks using a specific config
def find_decks_in_settings_group(config_id):
    decks = []
    for deck in mw.col.decks.all():
        if deck.get("conf_id") == config_id:
            decks.append(deck["id"])
    return decks


# Count new cards in settings group
def new_cards_in_settings_group(name):
    new_cards = 0
    new_today = 0

    # Get config id for the deck name
    deck_id = mw.col.decks.id_for_name(name)
    deck = mw.col.decks.get(deck_id)
    config_id = deck.get("conf_id")

    if config_id:
        # Find all decks using this config
        decks = find_decks_in_settings_group(config_id)
        for d in decks:
            new_cards += new_cards_in_deck(d)
            new_today += first_seen_cards_in_deck(d)
    return new_cards, new_today


# Count cards first seen today
def first_seen_cards_in_deck(deck_id):
    day_cutoff = mw.col.sched.day_cutoff
    return (
        mw.col.db.scalar(
            """
        SELECT count() FROM (
            SELECT r.id as review, c.id as card, c.did as deck
            FROM revlog r, cards c
            WHERE r.cid = c.id
            AND r.type = 0
            AND r.id >= ?
            AND deck = ?
            GROUP BY c.id
        )""",
            day_cutoff * 1000,
            deck_id,
        )
        or 0
    )


# find days until deadline
def days_until_deadline(deadline_date, include_today=True):
    if not deadline_date:
        # No deadline date
        return False
    date_format = "%Y-%m-%d"
    today = datetime.datetime.today()
    deadline_date = datetime.datetime.strptime(deadline_date, date_format)
    delta = deadline_date - today
    if include_today:
        days_left = delta.days + 1  # includes today
    else:
        days_left = delta.days  # today not included
    if days_left < 1:
        days_left = 0
    return days_left


# calculate cards per day
def cards_per_day(new_cards, days_left):
    if new_cards % days_left == 0:
        per_day = int(new_cards / days_left)
    else:
        per_day = int(new_cards / days_left) + 1
    # sanity check
    if per_day < 0:
        per_day = 0
    return per_day


def update_new_cards_per_day(name, per_day):
    """Update deck-specific new cards and review limits"""
    # Get deck ID from name
    deck_id = mw.col.decks.id_for_name(name)
    if not deck_id:
        return

    # Get the deck
    deck = mw.col.decks.get(deck_id)
    if not deck:
        return

    # Update both the new cards per day limit and review limit
    deck["newLimit"] = int(per_day)  # Set the deck-specific override
    deck["reviewLimit"] = int(per_day * 10)  # Set review limit

    # Save deck changes
    mw.col.decks.save(deck)

    # Also update the config for consistency
    config_id = deck.get("conf_id")
    if config_id:
        config = mw.col.decks.get_config(config_id)
        if config:
            config["new"]["perDay"] = int(per_day)
            mw.col.decks.update_config(config)

    # Ensure changes are saved
    mw.col.save()
    mw.reset()


def calc_new_cards_per_day(name, days_left, silent=True):
    """Calculate and update the number of new cards per day"""
    new_cards, new_today = new_cards_in_settings_group(name)
    total_cards = new_cards + new_today

    if days_left <= 0:
        per_day = total_cards  # Show all remaining cards if past deadline
    else:
        per_day = cards_per_day(total_cards, days_left)

    # Update deck configuration
    update_new_cards_per_day(name, per_day)

    return (name, new_today, new_cards, days_left, per_day)


def allDeadlines(silent=True):
    """Process all deadlines and update deck configurations"""
    deadlines = mw.addonManager.getConfig(__name__)
    deadlines.pop("test", None)

    if "deadlines" not in deadlines:
        temp = {"deadlines": {}}
        for profile, profile_deadlines in deadlines.items():
            temp["deadlines"][profile] = profile_deadlines
        deadlines = temp
        mw.addonManager.writeConfig(__name__, deadlines)

    profile = str(aqt.mw.pm.name)
    include_today = True
    tempLogString = ""

    if profile in deadlines["deadlines"]:
        for deck, date in deadlines["deadlines"].get(profile).items():
            days_left = days_until_deadline(date, include_today)
            if days_left is not False:
                (name, new_today, new_cards, days_left, per_day) = (
                    calc_new_cards_per_day(deck, days_left, silent)
                )
                if deadlines.get("oneOrMany", "") == "Many":
                    if not silent:
                        logString = f"{name}\n\nNew cards seen today: {new_today}\nNew cards remaining: {new_cards}\nDays left: {days_left}\nNew cards per day: {per_day}"
                        utils.showInfo(logString)
                else:
                    tempLogString += f"{name}\nNew cards seen today: {new_today}\nNew cards remaining: {new_cards}\nDays left: {days_left}\nNew cards per day: {per_day}\n\n"

    if deadlines.get("oneOrMany", "One") == "One" and not silent:
        summaryPopup(tempLogString)

    # Make sure all changes are saved and refresh UI
    mw.col.save()
    mw.reset()


# Manual Version
def manualDeadlines():
    allDeadlines(False)


def summaryPopup(text):
    parent = aqt.mw.app.activeWindow() or aqt.mw
    popup = QDialog(parent)
    popup.resize(500, 500)
    layout = QVBoxLayout()
    scroll = QScrollArea()
    textbox = QLabel(text)
    scroll.setWidget(textbox)
    scroll.ensureWidgetVisible(textbox)
    layout.addWidget(scroll)
    okButton = QDialogButtonBox.StandardButton.Ok
    buttonBox = QDialogButtonBox(okButton)
    buttonBox.button(okButton).clicked.connect(closeSummary)
    layout.addWidget(buttonBox)
    popup.setLayout(layout)
    popup.show()


def closeSummary():
    aqt.mw.app.activeWindow().close()


manualDeadlineAction = QAction("Process Deadlines", mw)
manualDeadlineAction.triggered.connect(manualDeadlines)
configAction = QAction("Configure Deadlines", mw)
configAction.triggered.connect(DeadlineDialog)
DeadlineMenu.addAction(configAction)
DeadlineMenu.addAction(manualDeadlineAction)

# Add hook to adjust Deadlines on load profile
addHook("profileLoaded", allDeadlines)

