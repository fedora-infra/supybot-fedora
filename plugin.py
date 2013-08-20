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
import requests

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
from fedora.client.pkgdb import PackageDB

from kitchen.text.converters import to_unicode

import fedmsg.config
import fedmsg.meta

import simplejson
import urllib
import commands
import urllib2
import socket
import pytz
import calendar
import datetime

from __init__ import __version__


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
        self.pkgdb = PackageDB()
        # URLs
        #self.url = {}

        # fetch necessary caches
        self._refresh()

        # Pull in /etc/fedmsg.d/ so we can build the fedmsg.meta processors.
        fm_config = fedmsg.config.load_config()
        fedmsg.meta.make_processors(**fm_config)

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
        self.bugzacl = self.pkgdb.get_bugzilla_acls()
        socket.setdefaulttimeout(timeout)

    def refresh(self, irc, msg, args):
        """takes no arguments

        Refresh the necessary caches."""
        self._refresh()
        irc.replySuccess()
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

    def branches(self, irc, msg, args, package):
        """<package>

        Return the branches a package is in."""
        try:
            pkginfo = self.pkgdb.get_package_info(package)
        except AppError:
            irc.reply("No such package exists.")
            return
        branch_list = []
        for listing in pkginfo['packageListings']:
            branch_list.append(listing['collection']['branchname'])
        branch_list.sort()
        irc.reply(' '.join(branch_list))
        return
    branches = wrap(branches, ['text'])

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
        find_name = to_unicode(find_name)
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

    def hellomynameis(self, irc, msg, args, name):
        """<username>

        Return brief information about a Fedora Account System username. Useful
        for things like meeting roll call and calling attention to yourself."""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Something blew up, please try again')
            return
        if not person:
            irc.reply('Sorry, but you don\'t exist')
            return
        irc.reply(('%(username)s \'%(human_name)s\' <%(email)s>' %
                   person).encode('utf-8'))
    hellomynameis = wrap(hellomynameis, ['text'])

    def himynameis(self, irc, msg, args, name):
        """<username>

        Will the real Slim Shady please stand up?"""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Something blew up, please try again')
            return
        if not person:
            irc.reply('Sorry, but you don\'t exist')
            return
        irc.reply(('%(username)s \'Slim Shady\' <%(email)s>' %
                   person).encode('utf-8'))
    himynameis = wrap(himynameis, ['text'])

    def localtime(self, irc, msg, args, name):
        """<username>

        Returns the current time of the user.
        The timezone is queried from FAS."""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Error getting info user user: "%s"' % name)
            return
        if not person:
            irc.reply('User "%s" doesn\'t exist' % name)
            return
        timezone_name = person['timezone']
        if timezone_name is None:
            irc.reply('User "%s" doesn\'t share his timezone' % name)
            return
        try:
            time = datetime.datetime.now(pytz.timezone(timezone_name))
        except:
            irc.reply('The timezone of "%s" was unknown: "%s"' % (name,
                                                                  timezone))
            return
        irc.reply('The current local time of "%s" is: "%s" (timezone: %s)' %
                  (name, time.strftime('%H:%M'), timezone_name))
    localtime = wrap(localtime, ['text'])

    def fasinfo(self, irc, msg, args, name):
        """<username>

        Return information on a Fedora Account System username."""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Error getting info for user: "%s"' % name)
            return
        if not person:
            irc.reply('User "%s" doesn\'t exist' % name)
            return
        person['creation'] = person['creation'].split(' ')[0]
        string = ("User: %(username)s, Name: %(human_name)s"
                  ", email: %(email)s, Creation: %(creation)s"
                  ", IRC Nick: %(ircnick)s, Timezone: %(timezone)s"
                  ", Locale: %(locale)s"
                  ", GPG key ID: %(gpg_keyid)s, Status: %(status)s") % person
        irc.reply(string.encode('utf-8'))

        # List of unapproved groups is easy
        unapproved = ''
        for group in person['unapproved_memberships']:
            unapproved = unapproved + "%s " % group['name']
        if unapproved != '':
            irc.reply('Unapproved Groups: %s' % unapproved)

        # List of approved groups requires a separate query to extract roles
        constraints = {'username': name, 'group': '%',
                       'role_status': 'approved'}
        columns = ['username', 'group', 'role_type']
        roles = []
        try:
            roles = self.fasclient.people_query(constraints=constraints,
                                                columns=columns)
        except:
            irc.reply('Error getting group memberships.')
            return

        approved = ''
        for role in roles:
            if role['role_type'] == 'sponsor':
                approved += '+' + role['group'] + ' '
            elif role['role_type'] == 'administrator':
                approved += '@' + role['group'] + ' '
            else:
                approved += role['group'] + ' '
        if approved == '':
            approved = "None"

        irc.reply('Approved Groups: %s' % approved)
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

    def admins(self, irc, msg, args, name):
        """<group short name>

        Return the administrators list for the selected group"""

        try:
            group = self.fasclient.group_members(name)
            sponsors = ''
            for person in group:
                if person['role_type'] == 'administrator':
                    sponsors += person['username'] + ' '
            irc.reply('Administrators for %s: %s' % (name, sponsors))
        except AppError:
            irc.reply('There is no group %s.' % name)

    admins = wrap(admins, ['text'])

    def sponsors(self, irc, msg, args, name):
        """<group short name>

        Return the sponsors list for the selected group"""

        try:
            group = self.fasclient.group_members(name)
            sponsors = ''
            for person in group:
                if person['role_type'] == 'sponsor':
                    sponsors += person['username'] + ' '
                elif person['role_type'] == 'administrator':
                    sponsors += '@' + person['username'] + ' '
            irc.reply('Sponsors for %s: %s' % (name, sponsors))
        except AppError:
            irc.reply('There is no group %s.' % name)

    sponsors = wrap(sponsors, ['text'])

    def members(self, irc, msg, args, name):
        """<group short name>

        Return a list of members of the specified group"""
        try:
            group = self.fasclient.group_members(name)
            members = ''
            for person in group:
                if person['role_type'] == 'administrator':
                    members += '@' + person['username'] + ' '
                elif person['role_type'] == 'sponsor':
                    members += '+' + person['username'] + ' '
                else:
                    members += person['username'] + ' '
            irc.reply('Members of %s: %s' % (name, members))
        except AppError:
            irc.reply('There is no group %s.' % name)

    members = wrap(members, ['text'])

    def showticket(self, irc, msg, args, baseurl, number):
        """<baseurl> <number>

        Return the name and URL of a trac ticket or bugzilla bug.
        """
        url = format(baseurl, str(number))
        size = conf.supybot.protocols.http.peekSize()
        text = utils.web.getUrl(url, size=size)
        parser = Title()
        try:
            parser.feed(text)
        except sgmllib.SGMLParseError:
            irc.reply(format('Encountered a problem parsing %u', url))
        if parser.title:
            irc.reply(utils.web.htmlToText(parser.title.strip()) + ' - ' + url)
        else:
            irc.reply(format('That URL appears to have no HTML title ' +
                             'within the first %i bytes.', size))
    showticket = wrap(showticket, ['httpUrl', 'int'])

    def swedish(self, irc, msg, args):
        """takes no arguments

        Humor mmcgrath."""
        irc.reply(str('kwack kwack'))
        irc.reply(str('bork bork bork'))
        irc.reply(str('(supybot-fedora version %s)' % __version__))
    swedish = wrap(swedish)

    def wikilink(self, irc, msg, args, name):
        """<username>

        Return MediaWiki link syntax for a FAS user's page on the wiki."""
        try:
            person = self.fasclient.person_by_username(name)
        except:
            irc.reply('Error getting info for user: "%s"' % name)
            return
        if not person:
            irc.reply('User "%s" doesn\'t exist' % name)
            return
        string = "[[User:%s|%s]]" % (person["username"],
                                     person["human_name"] or '')
        irc.reply(string.encode('utf-8'))
    wikilink = wrap(wikilink, ['text'])

    def mirroradmins(self, irc, msg, args, hostname):
        """<hostname>

        Return MirrorManager list of FAS usernames which administer <hostname>.
        <hostname> must be the FQDN of the host."""
        url = ("https://admin.fedoraproject.org/mirrormanager/mirroradmins?"
               "tg_format=json&host=" + hostname)
        result = self._load_json(url)['values']
        if len(result) == 0:
            irc.reply('Hostname "%s" not found' % hostname)
            return
        string = 'Mirror Admins of %s: ' % hostname
        string += ' '.join(result)
        irc.reply(string.encode('utf-8'))
    mirroradmins = wrap(mirroradmins, ['text'])

    def quote(self, irc, msg, args, arguments):
        """<SYMBOL> [daily, weekly, monthly]

        Return some datagrepper statistics on fedmsg categories.
        """

        # First, some argument parsing.  Supybot should be able to do this for
        # us, but I couldn't figure it out.  The supybot.plugins.additional
        # object is the thing to use... except its weird.
        tokens = arguments.split(None, 1)
        if len(tokens) == 1:
            symbol, frame = tokens[0], 'daily'
        else:
            symbol, frame = tokens

        # Second, build a lookup table for symbols.  By default, we'll use the
        # fedmsg category names, take their first 3 characters and uppercase
        # them.  That will take things like "wiki" and turn them into "WIK" and
        # "bodhi" and turn them into "BOD".  This handles a lot for us.  We'll
        # then override those that don't make sense manually here.  For
        # instance "fedoratagger" by default would be "FED", but that's no
        # good.  We want "TAG".
        # Why all this trouble?  Well, as new things get added to the fedmsg
        # bus, we don't want to have keep coming back here and modifying this
        # code.  Hopefully this dance will at least partially future-proof us.
        symbols = dict([
            (processor.__name__.lower(), processor.__name__[:3].upper())
            for processor in fedmsg.meta.processors
        ])
        symbols.update({
            'fedoratagger': 'TAG',
            'fedbadges': 'BDG',
            'buildsys': 'KOJ',
            'pkgdb': 'PKG',
            'meetbot': 'MTB',
            'planet': 'PLN',
            'trac': 'TRC',
            'mailman': 'MM3',
        })

        # Now invert the dict so we can lookup the argued symbol.
        # Yes, this is vulnerable to collisions.
        symbols = dict([(sym, name) for name, sym in symbols.items()])

        # These aren't user-facing topics, so drop 'em.
        del symbols['LOG']
        del symbols['UNH']
        del symbols['ANN']  # And this one is unused...

        key_fmt = lambda d: ', '.join(sorted(d.keys()))

        if not symbol in symbols:
            response = "No such symbol %r.  Try one of %s"
            irc.reply((response % (symbol, key_fmt(symbols))).encode('utf-8'))
            return

        # Now, build another lookup of our various timeframes.
        frames = dict(
            daily=datetime.timedelta(days=1),
            weekly=datetime.timedelta(days=7),
            monthly=datetime.timedelta(days=30),
        )

        if not frame in frames:
            response = "No such timeframe %r.  Try one of %s"
            irc.reply((response % (frame, key_fmt(frames))).encode('utf-8'))
            return

        category = [symbols[symbol]]

        t2 = datetime.datetime.now()
        t1 = t2 - frames[frame]
        t0 = t1 - frames[frame]

        # Count the number of messages between t0 and t1, and between t1 and t2
        count1 = Datagrepper.query(t0, t1, category=category)
        count2 = Datagrepper.query(t1, t2, category=category)

        phrases = dict(
            daily="yesterday",
            weekly="last week",
            monthly="last month",
        )

        if count1 and count2:
            percent = ((float(count2) / count1) - 1) * 100
        elif not count1 and count2:
            # If the older of the two time periods had zero messages, but there
            # are some in the more current period.. well, that's an infinite
            # percent increase.
            percent = float('inf')
        elif not count1 and not count2:
            # If counts are zero for both periods, then the change is 0%.
            percent = 0
        else:
            # Else, if there were some messages in the old time period, but
            # none in the current... then that's a 100% drop off.
            percent = -100

        sign = lambda value: value >= 0 and '+' or '-'

        response = "{sym}, {name} {sign}{percent:.2f}% over {phrase}".format(
            sym=symbol,
            name=symbols[symbol],
            sign=sign(percent),
            percent=abs(percent),
            phrase=phrases[frame],
        )

        irc.reply(response.encode('utf-8'))
    quote = wrap(quote, ['text'])


class Datagrepper(object):
    """ Some datagrepper utilities for the "quote" command. """

    datagrepper_url = 'https://apps.fedoraproject.org/datagrepper/raw'

    @classmethod
    def query(cls, start, end, **kwargs):
        """ Return the count of msgs filtered by kwargs for a given time. """
        params = {
            'start': calendar.timegm(start.timetuple()),
            'end': calendar.timegm(end.timetuple()),
        }
        params.update(kwargs)

        req = requests.get(cls.datagrepper_url, params=params)
        json_out = simplejson.loads(req.text)
        result = int(json_out['total'])
        return result


Class = Fedora


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
