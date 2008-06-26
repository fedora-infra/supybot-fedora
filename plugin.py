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

import sgmllib
import htmlentitydefs

import supybot.utils as utils
import supybot.conf as conf
import time
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks

from fedora.client import AuthError, ServerError
from fedora.accounts.fas2 import AccountSystem

import simplejson
import urllib
import commands


class Title(sgmllib.SGMLParser):
    entitydefs = htmlentitydefs.entitydefs.copy()
    entitydefs['nbsp'] = ' '
    def __init__(self):
        self.inTitle = False
        self.title = ''
        sgmllib.SGMLParser.__init__(self)

    def start_title(self, attrs):
        self.inTitle = True

    def end_title(self):
        self.inTitle = False

    def unknown_entityref(self, name):
        if self.inTitle:
            self.title += ' '

    def unknown_charref(self, name):
        if self.inTitle:
            self.title += ' '

    def handle_data(self, data):
        if self.inTitle:
            self.title += data


class Fedora(callbacks.Plugin):
    """Add the help for "@plugin help Fedora" here
    This should describe *how* to use this plugin."""
    threaded = True

    # Our owners list
    owners = None

    # Timestamp of our owners data
    owners_timestamp = None

    # Cache time of owners list, in seconds
    owners_cache = 259200

    # /group/dump/
    groupdump = None

    # Timestamp of /group/dump/ data
    groupdump_timestamp = None

    # Cache time of groupdump, in seconds
    groupdump_cache = 1800

    # To get the information, we need a username and password to FAS.
    # DO NOT COMMIT YOUR USERNAME AND PASSWORD TO THE PUBLIC REPOSITORY!
    username = ''
    password = ''

    # URLs
    url = {}
    # use fas2 for groupdump
    url["owners"] = "https://admin.fedoraproject.org/pkgdb/acls/bugzilla?tg_format=plain"

    fasclient = AccountSystem('https://admin.fedoraproject.org/accounts/', username, password)

    def _getowners(self):
        """
        Return the owners list.  If it's not already cached, grab it from
        self.url["owners"], and use it for self.owners_timestamp days
        """
        if self.owners != None:
            if (time.time() - self.owners_timestamp) <= self.owners_cache*86400:
                return self.owners
        self.owners = urllib2.urlopen(self.url["owners"]).read()
        self.owners_timestamp = time.time()
        return self.owners

    def whoowns(self, irc, msg, args, package):
        """<package>

        Retrieve the owner of a given package
        """
        owners_list = self._getowners()
        owner = None
        for line in owners_list.split('\n'):
            entry = line.strip().split('|')
            if len(entry) >= 5:
                if entry[1] == package:
                    owner = entry[3]
                    break
        irc.reply("%s" % owner)
    whoowns = wrap(whoowns, ['text'])

   

    def fas(self, irc, msg, args, name):
        if self.groupdump != None:
            if (time.time() - self.groupdump_timestamp) <= self.groupdump_cache:
                self.groupdump = self.fasclient.people_by_id()
                self.groupdump_timestamp = time.time()
        find_name = name
        found = 0
        mystr = []
        for f in self.groupdump:
            username = self.groupdump[f]['username']
            email = self.groupdump[f]['email']
            name = self.groupdump[f]['human_name']
            if username == find_name.lower() or email.lower().find(find_name.lower()) != -1 or name.lower().find(find_name.lower()) != -1:
                mystr.append(str("%s '%s' <%s>" % (username, name, email)))
        if len(mystr) == 0:
            irc.reply(str("'%s' Not Found!" % find_name))
        else:
            irc.reply(' - '.join(mystr))
    fas = wrap(fas, ['text'])

    def fasinfo(self, irc, msg, args, name):
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply(str('Error getting info for user: "%s"' % name))
            return
        string = "User: %s, Name: %s, email: %s Creation: %s, IRC Nick: %s, Timezone: %s, Locale: %s, Extension: 5%s" % (person['username'], person['human_name'], person['email'], person['creation'].split(' ')[0], person['ircnick'], person['timezone'], person['locale'], person['id'])
        approved = ''
        for group in person['approved_memberships']:
            approved = approved + "%s " % group['name']

        unapproved = ''
        for group in person['unapproved_memberships']:
            unapproved = unapproved + "%s " % group['name']

        if approved == '':
            approved = "None"
        if unapproved == '':
            unapproved = "None"

        irc.reply(str(string.encode('utf-8')))
        irc.reply(str('Approved Groups: %s' % approved))
        irc.reply(str('Unapproved Groups: %s' % unapproved))
    fasinfo = wrap(fasinfo, ['text'])



    def ticket(self, irc, msg, args, num):
        """<url>

        Returns the HTML <title>...</title> of a URL.
        """
        url = 'https://fedorahosted.org/projects/fedora-infrastructure/ticket/%s' % num
        size = conf.supybot.protocols.http.peekSize()
        text = utils.web.getUrl(url, size=size)
        parser = Title()
        try:
            parser.feed(text)
        except sgmllib.SGMLParseError:
            self.log.debug('Encountered a problem parsing %u.  Title may '
                           'already be set, though', url)
        if parser.title:
            irc.reply(str("%s - https://fedorahosted.org/projects/fedora-infrastructure/ticket/%s" % (utils.web.htmlToText(parser.title.strip()), num) ))
        else:
            irc.reply(format('That URL appears to have no HTML title '
                             'within the first %i bytes.', size))
    ticket = wrap(ticket, ['int'])

    def rel(self, irc, msg, args, num):
        """<url>

        Returns the HTML <title>...</title> of a URL.
        """
        url = 'https://fedorahosted.org/projects/rel-eng/ticket/%s' % num
        size = conf.supybot.protocols.http.peekSize()
        text = utils.web.getUrl(url, size=size)
        parser = Title()
        try:
            parser.feed(text)
        except sgmllib.SGMLParseError:
            self.log.debug('Encountered a problem parsing %u.  Title may '
                           'already be set, though', url)
        if parser.title:
            irc.reply(str("%s - https://fedorahosted.org/projects/rel-eng/ticket/%s" % (utils.web.htmlToText(parser.title.strip()), num) ))
        else:
            irc.reply(format('That URL appears to have no HTML title '
                             'within the first %i bytes.', size))
    rel = wrap(rel, ['int'])


    def swedish(self, irc, msg, args):
        irc.reply(str('kwack kwack'))
        irc.reply(str('bork bork bork'))
    swedish = wrap(swedish)


    def bug(self, irc, msg, args, url):
        """<url>

        Returns the HTML <title>...</title> of a URL.
        """
        bugNum = url
        url = 'https://bugzilla.redhat.com/show_bug.cgi?id=%s' % url
        size = conf.supybot.protocols.http.peekSize()
        text = utils.web.getUrl(url, size=size)
        parser = Title()
        try:
            parser.feed(text)
        except sgmllib.SGMLParseError:
            self.log.debug('Encountered a problem parsing %u.  Title may '
                           'already be set, though', url)
        if parser.title:
            irc.reply("%s - https://bugzilla.redhat.com/%i" % (utils.web.htmlToText(parser.title.strip()), bugNum))
        else:
            irc.reply(format('That URL appears to have no HTML title '
                             'within the first %i bytes.', size))
    bug = wrap(bug, ['int'])


Class = Fedora


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
