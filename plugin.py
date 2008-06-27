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
from urllib2 import URLError


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
    """Use this plugin to retrieve Fedora-related information."""
    threaded = True

    def __init__(self, irc):
        super(Fedora, self).__init__(irc)

        # Our owners list
        self.owners = None

        # Timestamp of our owners data
        self.owners_timestamp = None

        # Cache time of owners list, in seconds
        self.owners_cache = 259200

        # /group/dump/
        self.userlist = None

        # Timestamp of /group/dump/ data
        self.userlist_timestamp = None

        # Cache time of userlist, in seconds
        self.userlist_cache = 1800

        # To get the information, we need a username and password to FAS.
        # DO NOT COMMIT YOUR USERNAME AND PASSWORD TO THE PUBLIC REPOSITORY!
        self.fasurl = self.registryValue('fas.url')
        self.username = self.registryValue('fas.username')
        self.password = self.registryValue('fas.password')

        self.fasclient = AccountSystem(self.fasurl, self.username,
                                       self.password)
        # URLs
        self.url = {}
        self.url["owners"] = "https://admin.fedoraproject.org/pkgdb/acls/" + \
                "bugzilla?tg_format=plain"

    def _getowners(self):
        """
        Return the owners list.  If it's not already cached, grab it from
        self.url["owners"], and use it for self.owners_timestamp seconds
        """
        if self.owners != None:
            if (time.time() - self.owners_timestamp) <= self.owners_cache:
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

    def fas(self, irc, msg, args, find_name):
        """<query>

        Search the Fedora Account System usernames, full names, and email
        addresses for a match."""
        if not self.userlist or (time.time() - self.userlist_timestamp) >= \
           self.userlist_cache:
            irc.reply("Just a moment, I need to rebuild the user cache...")
            try:
                self.userlist = self.fasclient.people_by_id()
            except URLError:
                irc.reply("There was an error getting user data. Please try "+\
                          "again.")
            #import cPickle
            #self.userlist = cPickle.load(open('/tmp/ricbot.data'))
            #cPickle.dump(self.userlist, open('/tmp/ricbot.data', 'w'))
            self.userlist_timestamp = time.time()
        mystr = []
        for user in self.userlist:
            username = self.userlist[user]['username']
            email = self.userlist[user]['email']
            name = self.userlist[user]['human_name']
            if username == find_name.lower() or \
               email.lower().find(find_name.lower()) != -1 or  \
               name.lower().find(find_name.lower()) != -1:
                mystr.append("%s '%s' <%s>" % (username, name, email))
        if len(mystr) == 0:
            irc.reply("'%s' Not Found!" % find_name)
        else:
            irc.reply(' - '.join(mystr).encode('utf-8'))
    fas = wrap(fas, ['text'])

    def fasinfo(self, irc, msg, args, name):
        """<username>

        Return information on a Fedora Account System username."""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Error getting info for user: "%s"' % name)
            return
        person['creation'] = person['creation'].split(' ')[0]
        string = ("User: %(username)s, Name: %(human_name)s" + \
            ", email: %(email)s, Creation: %(creation)s" + \
            ", IRC Nick: %(ircnick)s, Timezone: %(timezone)s" + \
            ", Locale: %(locale)s, Extension: 5%(id)s") % person
        approved = ''
        for group in person['approved_memberships']:
            approved += group['name'] + ' '

        unapproved = ''
        for group in person['unapproved_memberships']:
            unapproved = unapproved + "%s " % group['name']

        if approved == '':
            approved = "None"
        if unapproved == '':
            unapproved = "None"

        irc.reply(string.encode('utf-8'))
        irc.reply('Approved Groups: %s' % approved)
        irc.reply('Unapproved Groups: %s' % unapproved)
    fasinfo = wrap(fasinfo, ['text'])

    def _ticketer(self, baseurl, num):
        url = format(baseurl, str(num))
        size = conf.supybot.protocols.http.peekSize()
        text = utils.web.getUrl(url, size=size)
        parser = Title()
        try:
            parser.feed(text)
        except sgmllib.SGMLParseError:
            return format('Encountered a problem parsing %u. Title may ' +
                          'already be set, though', url)
        if parser.title:
            return utils.web.htmlToText(parser.title.strip()) + ' - ' + url
        else:
            return format('That URL appears to have no HTML title ' +
                          'within the first %i bytes.', size)

    def ticket(self, irc, msg, args, num):
        """<number>

        Return the name and URL of a Fedora Infrastructure ticket.
        """
        baseurl = 'https://fedorahosted.org/projects/fedora-infrastructure/'+\
                'ticket/%s'
        irc.reply(self._ticketer(baseurl, num))
    ticket = wrap(ticket, ['int'])

    def rel(self, irc, msg, args, num):
        """<number>

        Return the name and URL of a rel-eng ticket.
        """
        baseurl = 'https://fedorahosted.org/projects/rel-eng/ticket/%s'
        irc.reply(self._ticketer(baseurl, num))
    rel = wrap(rel, ['int'])

    def swedish(self, irc, msg, args):
        """takes no arguments

        Humor mmcgrath."""
        irc.reply(str('kwack kwack'))
        irc.reply(str('bork bork bork'))
    swedish = wrap(swedish)

    def bug(self, irc, msg, args, num):
        """<number>

        Return the name and URL of a Red Hat Bugzilla ticket.
        """
        baseurl = 'https://bugzilla.redhat.com/show_bug.cgi?id=%s'
        irc.reply(self._ticketer(baseurl, num))
    bug = wrap(bug, ['int'])


Class = Fedora


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
