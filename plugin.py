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

from fedora.client import AppError
from fedora.client import AuthError
from fedora.client import ServerError
from fedora.client.fas2 import AccountSystem
from fedora.client.fas2 import FASError

import simplejson
import urllib
import commands
import urllib2
import socket


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

        # caches, automatically downloaded on __init__, manually refreshed on
        # .refresh
        self.userlist = None
        self.bugzacl = None

        # To get the information, we need a username and password to FAS.
        # DO NOT COMMIT YOUR USERNAME AND PASSWORD TO THE PUBLIC REPOSITORY!
        self.fasurl = self.registryValue('fas.url')
        self.username = self.registryValue('fas.username')
        self.password = self.registryValue('fas.password')

        self.fasclient = AccountSystem(self.fasurl, username=self.username,
                                       password=self.password)
        # URLs
        self.url = {}
        self.url["bugzacl"] = "https://admin.fedoraproject.org/pkgdb/acls/"+\
                "bugzilla?tg_format=json"

        # fetch necessary caches
        self._refresh()

    def _refresh(self):
        timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(None)
        self.log.info("Downloading user data")
        request = self.fasclient.send_request('/user/list',
                                              req_params={'search': '*'},
                                              auth=True)
        users = request['people'] + request['unapproved_people']
        del request
        self.log.info("Caching necessary user data")
        self.users = {}
        self.faslist = {}
        for user in users:
            name = user['username']
            self.users[name] = {}
            self.users[name]['id'] = user['id']
            key = ' '.join([user['username'], user['email'] or '',
                            user['human_name'] or '', user['ircnick'] or ''])
            key = key.lower()
            value = "%s '%s' <%s>" % (user['username'], user['human_name'] or
                                      '', user['email'] or '')
            self.faslist[key] = value
        self.log.info("Downloading package owners cache")
        self.bugzacl = self._load_json(self.url["bugzacl"])['bugzillaAcls']
        socket.setdefaulttimeout(timeout)
        #json = simplejson.loads(file("/tmp/bugzilla", "r").read())
        #self.bugzacl = json['bugzillaAcls']

    def refresh(self, irc, msg, args):
        """takes no arguments

        Refresh the necessary caches."""
        self._refresh()
    refresh = wrap(refresh)

    def _load_json(self, url):
        timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(45)
        json = simplejson.loads(utils.web.getUrl(url))
        socket.setdefaulttimeout(timeout)
        return json

    def whoowns(self, irc, msg, args, package):
        """<package>

        Retrieve the owner of a given package
        """
        try:
            mainowner = self.bugzacl['Fedora'][package]['owner']
        except KeyError:
            irc.reply("No such package exists.")
            return
        others = []
        for key in self.bugzacl.keys():
            if key == 'Fedora':
                continue
            try:
                owner = self.bugzacl[key][package]['owner']
                if owner == mainowner:
                    continue
            except KeyError:
                continue
            others.append("%s in %s" % (owner, key))
        if others == []:
            irc.reply(mainowner)
        else:
            irc.reply("%s (%s)" % (mainowner, ', '.join(others)))
    whoowns = wrap(whoowns, ['text'])

    def what(self, irc, msg, args, package):
        """<package>

        Returns a description of a given package.
        """
        try:
            summary = self.bugzacl['Fedora'][package]['summary']
            irc.reply("%s: %s" % (package, summary))
        except KeyError:
            irc.reply("No such package exists.")
            return
    what = wrap(what, ['text'])

    def fas(self, irc, msg, args, find_name):
        """<query>

        Search the Fedora Account System usernames, full names, and email
        addresses for a match."""
        matches = []
        for entry in self.faslist.keys():
            if entry.find(find_name.lower()) != -1:
                matches.append(entry)
        if len(matches) == 0:
            irc.reply("'%s' Not Found!" % find_name)
        else:
            output = []
            for match in matches:
                output.append(self.faslist[match])
            irc.reply(' - '.join(output).encode('utf-8'))
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

    def group(self, irc, msg, args, name):
        """<group short name>

        Return information about a Fedora Account System group."""
        try:
            group = self.fasclient.group_by_name(name)
            irc.reply('%s: %s' %
                      (name, group['display_name']))
        except AppError:
            irc.reply('There is no group "%s".' % name)
    group = wrap(group, ['text'])

    def ext(self, irc, msg, args, name):
        """<username>

        Return the talk.fedoraproject.org extension number for a Fedora Account
        System username."""
        if name in self.users.keys():
            irc.reply('5' + str(self.users[name]['id']))
        else:
            irc.reply("User %s doesn't exist" % name)
    ext = wrap(ext, ['text'])

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
        baseurl = 'https://fedorahosted.org/fedora-infrastructure/ticket/%s'
        irc.reply(self._ticketer(baseurl, num))
    ticket = wrap(ticket, ['int'])

    def rel(self, irc, msg, args, num):
        """<number>

        Return the name and URL of a rel-eng ticket.
        """
        baseurl = 'https://fedorahosted.org/rel-eng/ticket/%s'
        irc.reply(self._ticketer(baseurl, num))
    rel = wrap(rel, ['int'])

    def bug(self, irc, msg, args, num):
        """<number>

        Return the name and URL of a Red Hat Bugzilla ticket.
        """
        baseurl = 'https://bugzilla.redhat.com/show_bug.cgi?id=%s'
        irc.reply(self._ticketer(baseurl, num))
    bug = wrap(bug, ['int'])

    def swedish(self, irc, msg, args):
        """takes no arguments

        Humor mmcgrath."""
        irc.reply(str('kwack kwack'))
        irc.reply(str('bork bork bork'))
    swedish = wrap(swedish)

    def wikilink(self, irc, msg, args, name):
        """<username>

        Return MediaWiki link syntax for a FAS user's page on the wiki."""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Error getting info for user: "%s"' % name)
            return
        username = person["username"][0].capitalize()+person["username"][1:]
        string = "[[User:%s|%s]]" % (username, person["human_name"])
        irc.reply(string.encode('utf-8'))
    wikilink = wrap(wikilink, ['text'])


Class = Fedora


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
