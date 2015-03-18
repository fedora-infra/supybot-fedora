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

import supybot.conf as conf
import supybot.registry as registry


def configure(advanced):
    # This will be called by supybot to configure this module.  advanced is
    # a bool that specifies whether the user identified himself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('Fedora', True)


Fedora = conf.registerPlugin('Fedora')
# This is where your configuration variables (if any) should go.  For example:
# conf.registerGlobalValue(Fedora, 'someConfigVariableName',
#     registry.Boolean(False, """Help for someConfigVariableName."""))
conf.registerGroup(Fedora, 'fas')
conf.registerGlobalValue(
    Fedora.fas, 'url',
    registry.String('https://admin.fedoraproject.org/accounts/',
                    """URL for the Fedora Account System"""))
conf.registerGlobalValue(
    Fedora.fas, 'username',
    registry.String('', """Username for the Fedora Account System""",
                    private=True))
conf.registerGlobalValue(
    Fedora.fas, 'password',
    registry.String('', """Password for the Fedora Account System""",
                    private=True))

conf.registerGroup(Fedora, 'github')
conf.registerGlobalValue(
    Fedora.github, 'oauth_token',
    registry.String('', """OAuth Token for the GitHub""",
                    private=True))


conf.registerGroup(Fedora, 'karma')
conf.registerGlobalValue(
    Fedora.karma, 'db_path',
    registry.String('/var/tmp/supybot-karma.db',
                    """Path to a karma db on disk"""))
# Here, 'unaddressed' commands are ones that are not directly addressed to the
# supybot nick.  I.e., if this is set to False, then you must say
#   'zodbot: pingou++'
# If it it set to True, then you may say
#   'pingou++'
conf.registerGlobalValue(
    Fedora.karma, 'unaddressed',
    registry.Boolean(True, "Allow unaddressed karma commands"))
conf.registerGlobalValue(
    Fedora.karma, 'allow_negative',
    registry.Boolean(True, "Allow negative karma to be given"))


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
