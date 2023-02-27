import os
import pathlib
import random
import re
from datetime import datetime, timedelta
from typing import NoReturn

import pynotification

from jarvis.executors import communicator
from jarvis.modules.audio import listener, speaker
from jarvis.modules.conditions import conversation
from jarvis.modules.logger.custom_logger import logger
from jarvis.modules.models import models
from jarvis.modules.utils import shared, util


def create_reminder(hour, minute, am_pm, message, to_about, timer: str = None) -> NoReturn:
    """Creates the lock file necessary to set a reminder.

    Args:
        hour: Hour of reminder time.
        minute: Minute of reminder time.
        am_pm: AM/PM of reminder time.
        message: Message to be reminded for.
        to_about: remind to or remind about as said in phrase.
        timer: Number of minutes/hours to reminder.
    """
    if not os.path.isdir('reminder'):
        os.mkdir('reminder')
    pathlib.Path(os.path.join("reminder", f"{hour}_{minute}_{am_pm}|{message.replace(' ', '_')}.lock")).touch()
    if timer:
        logger.info("Reminder created for '{message}' at {hour}:{minute} {am_pm}".format(message=message, hour=hour,
                                                                                         minute=minute, am_pm=am_pm))
        speaker.speak(text=f"{random.choice(conversation.acknowledgement)}! "
                           f"I will remind you {to_about} {message}, after {timer}.")
    else:
        speaker.speak(text=f"{random.choice(conversation.acknowledgement)}! "
                           f"I will remind you {to_about} {message}, at {hour}:{minute} {am_pm}.")


def reminder(phrase: str) -> None:
    """Passes hour, minute, am/pm and reminder message to Reminder class which initiates a thread for reminder.

    Args:
        phrase: Takes the phrase spoken as an argument.
    """
    if models.settings.limited:
        speaker.speak(text="Reminder features are currently unavailable, as you're running on restricted mode.")
        return
    message = re.search(' to (.*) at ', phrase) or re.search(' about (.*) at ', phrase) or \
        re.search(' to (.*) after ', phrase) or re.search(' about (.*) after ', phrase) or \
        re.search(' to (.*) in ', phrase) or re.search(' about (.*) in ', phrase) or \
        re.search(' to (.*)', phrase) or re.search(' about (.*)', phrase)
    if not message:
        speaker.speak(text='Reminder format should be::Remind me to do something, at some time.')
        return
    to_about = 'about' if 'about' in phrase else 'to'
    if 'minute' in phrase or "now" in phrase:
        phrase = phrase.replace("a minute", "1 minute").replace("now", "1 minute")
        if minutes := util.extract_nos(input_=phrase, method=int):
            min_ = 'minutes' if minutes > 1 else 'minute'
            hour, minute, am_pm = (datetime.now() + timedelta(minutes=minutes)).strftime("%I %M %p").split()
            create_reminder(hour=hour, minute=minute, am_pm=am_pm, message=message.group(1).strip(),
                            timer=f"{minutes} {min_}", to_about=to_about)
            return
    elif 'hour' in phrase:
        if hours := util.extract_nos(input_=phrase, method=int):
            hour_ = 'hours' if hours > 1 else 'hour'
            hour, minute, am_pm = (datetime.now() + timedelta(hours=hours)).strftime("%I %M %p").split()
            create_reminder(hour=hour, minute=minute, am_pm=am_pm, message=message.group(1).strip(),
                            timer=f"{hours} {hour_}", to_about=to_about)
            return
    if not (extracted_time := util.extract_time(input_=phrase)):
        if shared.called_by_offline:
            speaker.speak(text='Reminder format should be::Remind me to do something, at some time.')
            return
        speaker.speak(text=f"When do you want to be reminded {models.env.title}?", run=True)
        if not (phrase := listener.listen()):
            return
        if not (extracted_time := util.extract_time(input_=phrase)):
            return
    message = message.group(1).strip()
    extracted_time = extracted_time[0]
    am_pm = extracted_time.split()[-1]
    am_pm = str(am_pm).replace('a.m.', 'AM').replace('p.m.', 'PM')
    remind_time = extracted_time.split()[0]
    if ":" in extracted_time:
        hour = int(remind_time.split(":")[0])
        minute = int(remind_time.split(":")[-1])
    else:
        hour = int(remind_time.split()[0])
        minute = 0
    # makes sure hour and minutes are two digits
    hour, minute = f"{hour:02}", f"{minute:02}"
    if int(hour) <= 12 and int(minute) <= 59:
        create_reminder(hour=hour, minute=minute, am_pm=am_pm, to_about=to_about, message=message)
    else:
        speaker.speak(text=f"A reminder at {hour}:{minute} {am_pm}? Are you an alien? "
                           f"I don't think a time like that exists on Earth.")


def reminder_executor(message: str) -> NoReturn:
    """Notifies user about the reminder and displays a notification on the device.

    Args:
        message: Takes the reminder message as an argument.

    See Also:
        - Personalized icons for `Linux OS <https://wiki.ubuntu.com/Artwork/BreatheIconSet/Icons>`__
    """
    title = "REMINDER from Jarvis"
    communicator.send_sms(user=models.env.gmail_user, password=models.env.gmail_pass, number=models.env.phone_number,
                          body=message, subject=title)
    pynotification.pynotifier(title=title, message=message, debug=True, logger=logger)