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

from __future__ import division, print_function, absolute_import

import argparse
import re
import sys
import time
import traceback
from collections import deque

from slackclient import SlackClient
from slackclient.server import SlackConnectionError

from sonny import __version__
from sonny.common.config import (
    CLOUDS,
    SLACK_TOKEN,
    SLACK_CHANNEL
)
from sonny.common.redis import SonnyRedis

assert SLACK_TOKEN is not None
assert SLACK_CHANNEL is not None
assert len(CLOUDS) > 0

RTM_READ_DELAY = 0.25
COMMANDS = ['help', 'status', 'show']
EXAMPLE_COMMAND = "help"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"


class Sonny:

    def __init__(self):
        self.slack_client = SlackClient(SLACK_TOKEN)
        self.channel = SLACK_CHANNEL
        self.starterbot_id = None

        self._redis = {}
        self._pubsub = {}
        for cloud in CLOUDS:
            self._redis[cloud] = redis = SonnyRedis(cloud)
            self._pubsub[cloud] = redis.pubsub(
                ignore_subscribe_messages=True)
            self._pubsub[cloud].subscribe([cloud])

        self.message_queue = {cloud: deque() for cloud in CLOUDS}
        self.message_queue['sonny'] = deque()
        self.last_post = time.time()

    def run(self):
        """
        Check for monitor messages and post them in slack channel.
        Re-connect in case of connection errors.
        """

        delay = 2
        while True:
            try:
                if self.slack_client.rtm_connect(with_team_state=False):
                    self.starterbot_id = \
                        self.slack_client.api_call("auth.test")["user_id"]

                    if delay == 2:
                        self.post_message('sonny initialized')
                        self.post_message(f'subscribed to clouds {CLOUDS}')
                    else:
                        self.post_message('sonny re-initialized')

                    while True:
                        command, channel = self.parse_bot_commands(
                            self.slack_client.rtm_read())
                        if command:
                            self.handle_command(command, channel)

                        for _, pubsub in self._pubsub.items():
                            message = pubsub.get_message()
                            self.post_message(message)

                        time.sleep(RTM_READ_DELAY)
            except SlackConnectionError as e:
                traceback.print_exc()
                print(f'Connection error, reconnecting in {delay} seconds')
            except Exception as e:
                traceback.print_exc()
                print(f'Connection exception, reconnecting in {delay} seconds')

            time.sleep(delay)
            delay *= delay

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
        default_response = f'not sure what you mean, try {COMMANDS}'

        response = None
        if command.startswith('help'):
            response = f'cmds: {COMMANDS}'
        elif command.startswith('show'):
            cmds = command.split(' ')
            response = 'usage: show {hv name|vm {uuid|name}}'
            if len(cmds) == 3 and any(cmds[1] == 'hv', cmds[1] == 'vm'):
                for cloud in CLOUDS:
                    response = self._redis.show(command)
                    if response:
                        break
                else:
                    response = 'not found'
        elif command.startswith('status'):
            response = []
            for cloud in CLOUDS:
                last_run_ts = self._redis[cloud].get(
                    'api_alive:timestamp', float)
                if not last_run_ts:
                    continue

                last_run_d = int(time.time() - last_run_ts)
                response.append(
                    f'{cloud}: inventory updated {last_run_d} seconds ago')

            response = '\n'.join(response)

        self.slack_client.api_call("chat.postMessage", channel=channel,
                                   text=response or default_response)

    def post_message(self, message):

        if isinstance(message, str):
            self.message_queue['sonny'].append(message)

        elif isinstance(message, dict):
            message_data = message['data'].decode('utf-8')
            cloud = message['channel'].decode('utf-8')
            self.message_queue[cloud].append(message_data)

        time_now = time.time()
        time_diff = time_now - self.last_post
        if time_diff < 1:
            return

        m_list = []
        for cloud in self.message_queue:
            while self.message_queue[cloud]:
                m = self.message_queue[cloud].popleft()
                m_list.append(cloud + ': ' + m)

        if not m_list:
            return

        self.slack_client.api_call(
            "chat.postMessage", channel=self.channel, text='\n'.join(m_list))
        self.last_post = time.time()

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


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(
        description="Sonny OpenStack Robot")
    parser.add_argument(
        '--version',
        action='version',
        version='sonny {ver}'.format(ver=__version__))
    return parser.parse_args(args)


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    Sonny().run()


def run():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
