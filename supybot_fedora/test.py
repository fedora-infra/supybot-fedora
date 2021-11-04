###
# Copyright (c) 2007, Mike McGrath
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import os
from unittest import mock
from tempfile import TemporaryDirectory

from supybot import test, world, conf

world.myVerbose = test.verbosity.MESSAGES


class FASJSONResult:
    def __init__(self, result):
        self.result = result


class FedoraTestCase(test.ChannelPluginTestCase):
    plugins = ("Fedora",)

    def setUp(self):
        conf.supybot.plugins.Fedora.fasjson.refresh_cache_on_startup.setValue(False)
        self.fasjson_client = mock.Mock()
        with mock.patch(
            "supybot_fedora.plugin.fasjson_client"
        ) as fasjson_client_module:
            fasjson_client_module.Client.return_value = self.fasjson_client
            super().setUp()
        self.instance = self.irc.getCallback("Fedora")
        self.tmpdir = TemporaryDirectory()
        conf.supybot.plugins.Fedora.karma.db_path.setValue(
            os.path.join(self.tmpdir.name, "karma.db")
        )

    def tearDown(self):
        self.tmpdir.cleanup()
        super().tearDown()

    def testRandom(self):
        self.assertRaises(ValueError)

    def testKarma(self):
        self.instance.users = ["dummy", "test"]
        self.instance.nickmap = {"dummy": "dummy"}
        expected = (
            "Karma for dummy changed to 1 (for the current release cycle):  "
            "https://badges.fedoraproject.org/badge/macaron-cookie-i"
        )
        self.assertResponse("dummy++", expected)

    def testKarmaActorNotInFAS(self):
        self.instance.users = ["dummy"]
        self.instance.nickmap = {"dummy": "dummy"}
        self.assertResponse("dummy++", "Couldn't find test in FAS")

    def testKarmaTargetNotInFAS(self):
        self.instance.users = ["test"]
        self.instance.nickmap = {}
        self.assertResponse("dummy++", "Couldn't find dummy in FAS")

    def testRefreshIRCNickFormat(self):
        nickformats = ["irc:/dummy", "irc://irc.libera.chat/dummy"]
        for nick in nickformats:
            result = FASJSONResult(
                [
                    {
                        "username": "dummy",
                        "emails": ["dummy@example.com"],
                        "ircnicks": [nick],
                        "human_name": None,
                    }
                ]
            )
            self.instance.fasjsonclient.list_users.return_value = result
            self.instance._refresh()
            self.assertEqual(self.instance.users, ["dummy"])
            self.assertEqual(self.instance.nickmap, {"dummy": "dummy"})


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
