#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Sonny
#
#    Copyright (C) 2018  Marko Kosmerl
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import time
import re

from threading import Thread

from redis import StrictRedis
from slackclient import SlackClient

# constants
RTM_READ_DELAY = 2  # x second delay between reading from RTM
EXAMPLE_COMMAND = "do"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"


class SlackBot(Thread):

    def __init__(self, token, channel):
        Thread.__init__(self)

        self.slack_client = SlackClient(token)
        self.redis = StrictRedis()
        self.channel = channel
        self.starterbot_id = None

    def run(self):
        """
        ...
        """
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.pubsub.subscribe('slack')

        if self.slack_client.rtm_connect(with_team_state=False):
            self.starterbot_id = \
                self.slack_client.api_call("auth.test")["user_id"]

            while True:
                command, channel = self.parse_bot_commands(
                    self.slack_client.rtm_read())
                if command:
                    self.handle_command(command, channel)

                message = self.pubsub.get_message()
                if message:
                    message_data = message['data'].decode('utf-8')
                    self.post_message(message_data)

                time.sleep(RTM_READ_DELAY)
        else:
            print("Connection failed. Exception traceback printed above.")

    def parse_bot_commands(self, slack_events):
        """
        Parses events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of
        command and channel.
        If its not found, then this function returns None, None.
        """
        for event in slack_events:
            if event["type"] == "message" and "subtype" not in event:
                user_id, message = self.parse_direct_mention(event["text"])
                if user_id == self.starterbot_id:
                    return message, event["channel"]
        return None, None

    def handle_command(self, command, channel):
        """
        Executes bot command if the command is known
        """
        # Default response is help text for the user
        default_response = "Not sure what you mean. Try *{}*.".format(
            EXAMPLE_COMMAND)

        response = None
        if command.startswith(EXAMPLE_COMMAND):
            response = "Sure...write some more code then I can do that!"

        # Sends the response back to the channel
        self.slack_client.api_call("chat.postMessage", channel=channel,
                                   text=response or default_response)

    def post_message(self, message):
        self.slack_client.api_call(
            "chat.postMessage", channel=self.channel, text=message)

    def parse_direct_mention(self, message_text):
        """
        Finds a direct mention (a mention that is at the beginning) in
        message text and returns the user ID which was mentioned.
        If there is no direct mention, returns None
        """
        matches = re.search(MENTION_REGEX, message_text)
        # the first group contains the username,
        # the second group contains the remaining message
        return (matches.group(1), matches.group(2).strip()) if matches \
            else (None, None)
