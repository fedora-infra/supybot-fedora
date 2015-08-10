# -*- coding: utf-8 -*-
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

import arrow
import sgmllib
import shelve
import htmlentitydefs
import requests
import time

# Use re2 if present.  It is faster.
try:
    import re2 as re
except ImportError:
    import re

import supybot.utils as utils
import supybot.conf as conf
import supybot.callbacks as callbacks
from supybot.commands import wrap

from fedora.client import AppError
from fedora.client.fas2 import AccountSystem
from pkgdb2client import PkgDB

from kitchen.text.converters import to_unicode

import fedmsg.config
import fedmsg.meta

import simplejson
import urllib
import socket
import pytz
import datetime
import threading

from itertools import chain, islice, tee
from operator import itemgetter

SPARKLINE_RESOLUTION = 50

datagrepper_url = 'https://apps.fedoraproject.org/datagrepper/raw'


def datagrepper_query(kwargs):
    """ Return the count of msgs filtered by kwargs for a given time.

    The arguments for this are a little clumsy; this is imposed on us by
    multiprocessing.Pool.
    """
    start, end = kwargs.pop('start'), kwargs.pop('end')
    params = {
        'start': time.mktime(start.timetuple()),
        'end': time.mktime(end.timetuple()),
    }
    params.update(kwargs)

    req = requests.get(datagrepper_url, params=params)
    json_out = simplejson.loads(req.text)
    result = int(json_out['total'])
    return result


class WorkerThread(threading.Thread):
    """ A simple worker thread for our threadpool. """

    def __init__(self, fn, item, *args, **kwargs):
        self.fn = fn
        self.item = item
        super(WorkerThread, self).__init__(*args, **kwargs)

    def run(self):
        self.result = self.fn(self.item)


class ThreadPool(object):
    """ Our very own threadpool implementation.

    We make our own thing because multiprocessing is too heavy.
    """

    def map(self, fn, items):
        threads = []

        for item in items:
            threads.append(WorkerThread(fn=fn, item=item))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        return [thread.result for thread in threads]


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
        self.pkgdb = PkgDB()
        # URLs
        # self.url = {}

        self.github_oauth_token = self.registryValue('github.oauth_token')

        self.karma_db_path = self.registryValue('karma.db_path')
        self.allow_unaddressed_karma = self.registryValue('karma.unaddressed')
        self.allow_negative = self.registryValue('karma.allow_negative')
        self.karma_tokens = ('++', '--') if self.allow_negative else ('++',)

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
                                              auth=True,
                                              timeout=240)
        users = request['people'] + request['unapproved_people']
        del request
        self.log.info("Caching necessary user data")
        self.users = {}
        self.faslist = {}
        self.nickmap = {}
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
            if user['ircnick']:
                self.nickmap[user['ircnick']] = name

        self.log.info("Downloading package owners cache")
        data = requests.get(
            'https://admin.fedoraproject.org/pkgdb/api/bugzilla?format=json',
            verify=True).json()
        self.bugzacl = data['bugzillaAcls']
        socket.setdefaulttimeout(timeout)

    def refresh(self, irc, msg, args):
        """takes no arguments

        Refresh the necessary caches."""

        irc.reply("Downloading caches.  This could take a while...")
        self._refresh()
        irc.replySuccess()
    refresh = wrap(refresh)

    def _load_json(self, url):
        timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(45)
        json = simplejson.loads(utils.web.getUrl(url))
        socket.setdefaulttimeout(timeout)
        return json

    def pulls(self, irc, msg, args, slug):
        """<username[/repo]>

        List the latest pending pull requests on github/pagure repos.
        """

        slug = slug.strip()
        if not slug or slug.count('/') != 0:
            irc.reply('Must be a GitHub org/username or pagure tag')
            return

        irc.reply('One moment, please...  Looking up %s.' % slug)
        fail_on_github, fail_on_pagure = False, False
        github_repos, pagure_repos = [], []
        try:
            github_repos = list(self.yield_github_repos(slug))
        except IOError as e:
            self.log.exception(e.message)
            fail_on_github = True

        try:
            pagure_repos = list(self.yield_pagure_repos(slug))
        except IOError as e:
            self.log.exception(e.message)
            fail_on_pagure = True

        if fail_on_github and fail_on_pagure:
            irc.reply('Could not find %s on GitHub or pagure.io' % slug)
            return

        results = sum([
            list(self.yield_github_pulls(slug, r)) for r in github_repos
        ], []) + sum([
            list(self.yield_pagure_pulls(slug, r)) for r in pagure_repos
        ], [])

        # Reverse-sort by time (newest-first)
        comparator = lambda a, b: cmp(b['age_numeric'], a['age_numeric'])
        results.sort(comparator)

        if not results:
            irc.reply('No pending pull requests on {slug}'.format(slug=slug))
        else:
            n = 6  # Show 6 pull requests
            for pull in results[:n]:
                irc.reply('@{user}\'s "{title}" {url} filed {age}'.format(
                    user=pull['user'],
                    title=pull['title'],
                    url=pull['url'],
                    age=pull['age'],
                ))

            if len(results) > n:
                irc.reply('... and %i more.' % (len(results) - n))
    pulls = wrap(pulls, ['text'])

    def yield_github_repos(self, username):
        self.log.info("Finding github repos for %r" % username)
        tmpl = "https://api.github.com/users/{username}/repos?per_page=100"
        url = tmpl.format(username=username)
        auth = dict(access_token=self.github_oauth_token)
        for result in self.yield_github_results(url, auth):
            yield result['name']

    def yield_github_pulls(self, username, repo):
        self.log.info("Finding github pull requests for %r %r" % (username, repo))
        tmpl = "https://api.github.com/repos/{username}/{repo}/" + \
            "pulls?per_page=100"
        url = tmpl.format(username=username, repo=repo)
        auth = dict(access_token=self.github_oauth_token)
        for result in self.yield_github_results(url, auth):
            yield dict(
                user=result['user']['login'],
                title=result['title'],
                url=result['html_url'],
                age=arrow.get(result['created_at']).humanize(),
                age_numeric=arrow.get(result['created_at']),
            )

    def yield_github_results(self, url, auth):
        results = []
        link = dict(next=url)
        while 'next' in link:
            response = requests.get(link['next'], params=auth)

            if response.status_code == 404:
                raise IOError("404 for %r" % link['next'])

            # And.. if we didn't get good results, just bail.
            if response.status_code != 200:
                raise IOError(
                    "Non-200 status code %r; %r; %r" % (
                        response.status_code, link['next'], response.json))

            results = response.json()

            for result in results:
                yield result

            field = response.headers.get('link', None)

            link = dict()
            if field:
                link = dict([
                    (
                        part.split('; ')[1][5:-1],
                        part.split('; ')[0][1:-1],
                    ) for part in field.split(', ')
                ])

    def yield_pagure_repos(self, tag):
        self.log.info("Finding pagure repos for %r" % tag)
        tmpl = "https://pagure.io/api/0/projects?tags={tag}"
        url = tmpl.format(tag=tag)
        for result in self.yield_pagure_results(url, 'projects'):
            yield result['name']

    def yield_pagure_pulls(self, tag, repo):
        self.log.info("Finding pagure pull requests for %r %r" % (tag, repo))
        tmpl = "https://pagure.io/api/0/{repo}/pull-requests"
        url = tmpl.format(tag=tag, repo=repo)
        for result in self.yield_pagure_results(url, 'requests'):
            yield dict(
                user=result['user']['name'],
                title=result['title'],
                url='https://pagure.io/{repo}/pull-request/{id}'.format(
                    repo=result['project']['name'], id=result['id']),
                age=arrow.get(result['date_created']).humanize(),
                age_numeric=arrow.get(result['date_created']),
            )

    def yield_pagure_results(self, url, key):
        response = requests.get(url)

        if response.status_code == 404:
            raise IOError("404 for %r" % url)

        # And.. if we didn't get good results, just bail.
        if response.status_code != 200:
            raise IOError(
                "Non-200 status code %r; %r; %r" % (
                    response.status_code, url, response.text))

        results = response.json()
        results = results[key]

        for result in results:
            yield result

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
        for key in self.bugzacl:
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
            pkginfo = self.pkgdb.get_package(package)
        except AppError:
            irc.reply("No such package exists.")
            return
        branch_list = []
        for listing in pkginfo['packages']:
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
            irc.reply('The timezone of "%s" was unknown: "%s"' % (
                name, timezone_name))
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

        # Import this here to avoid a circular import problem.
        from __init__ import __version__

        irc.reply(str('kwack kwack'))
        irc.reply(str('bork bork bork'))
        irc.reply(str('(supybot-fedora version %s)' % __version__))
    swedish = wrap(swedish)

    def invalidCommand(self, irc, msg, tokens):
        """ Handle any command not otherwise handled.

        We use this to accept karma commands directly.
        """
        channel = msg.args[0]
        if not irc.isChannel(channel):
            return

        agent = msg.nick
        line = tokens[-1].strip()
        words = line.split()
        for word in words:
            if word[-2:] in self.karma_tokens:
                self._do_karma(irc, channel, agent, word, line, explicit=True)

    def doPrivmsg(self, irc, msg):
        """ Handle everything.

        The name is misleading.  This hook actually gets called for all
        IRC activity in every channel.
        """
        # We don't handle this if we've been addressed because invalidCommand
        # will handle it for us.  This prevents us from accessing the db twice
        # and therefore crashing.
        if (msg.addressed or msg.repliedTo):
            return

        channel = msg.args[0]
        if irc.isChannel(channel) and self.allow_unaddressed_karma:
            irc = callbacks.SimpleProxy(irc, msg)
            agent = msg.nick
            line = msg.args[1].strip()

            # First try to handle karma commands
            words = line.split()
            for word in words:
                if word[-2:] in self.karma_tokens:
                    self._do_karma(
                        irc, channel, agent, word, line, explicit=False)

        blacklist = self.registryValue('naked_ping_channel_blacklist')
        if irc.isChannel(channel) and not channel in blacklist:
            # Also, handle naked pings for
            # https://github.com/fedora-infra/supybot-fedora/issues/26
            pattern = '\w* ?[:,] ?ping\W*$'
            if re.match(pattern, line):
                admonition = self.registryValue('naked_ping_admonition')
                irc.reply(admonition)

    def karma(self, irc, msg, args, name):
        """<username>

        Return the total karma for a FAS user."""
        data = None
        try:
            data = shelve.open(self.karma_db_path)
            votes = data['backwards'].get(name, {})
        finally:
            if data:
                data.close()

        inc = len([v for v in votes.values() if v == 1])
        dec = len([v for v in votes.values() if v == -1])
        total = inc - dec
        if inc or dec:
            irc.reply("Karma for %s has been increased %i times and "
                      "decreased %i times for a total of %i" % (
                        name, inc, dec, total))
        else:
            irc.reply("I have no karma data for %s" % name)

    karma = wrap(karma, ['text'])

    def _do_karma(self, irc, channel, agent, recip, line, explicit=False):
        recip, direction = recip[:-2], recip[-2:]
        if not recip:
            return

        # Extract 'puiterwijk' out of 'have a cookie puiterwijk++'
        recip = recip.strip().split()[-1]

        increment = direction == '++' # If not, then it must be decrement

        # Check that these are FAS users
        if not agent in self.nickmap and not agent in self.users:
            self.log.info(
                "Saw %s from %s, but %s not in FAS" % (recip, agent, agent))
            if explicit:
                irc.reply("Couldn't find %s in FAS" % agent)
            return

        if not recip in self.nickmap and not recip in self.users:
            self.log.info(
                "Saw %s from %s, but %s not in FAS" % (recip, agent, recip))
            if explicit:
                irc.reply("Couldn't find %s in FAS" % recip)
            return

        # Transform irc nicks into fas usernames if possible.
        if agent in self.nickmap:
            agent = self.nickmap[agent]

        if recip in self.nickmap:
            recip = self.nickmap[recip]

        if agent == recip:
            irc.reply("You may not modify your own karma.")
            return

        # Check our karma db to make sure this hasn't already been done.
        data = None
        try:
            data = shelve.open(self.karma_db_path)
            if 'forwards' not in data or 'backwards' not in data:
                data['forwards'], data['backwards'] = {}, {}

            if agent not in data['forwards']:
                forwards = data['forwards']
                forwards[agent] = {}
                data['forwards'] = forwards

            if recip not in data['backwards']:
                backwards = data['backwards']
                backwards[recip] = {}
                data['backwards'] = backwards

            vote = 1 if increment else -1

            if data['forwards'][agent].get(recip) == vote:
                ## People found this response annoying.
                ## https://github.com/fedora-infra/supybot-fedora/issues/25
                #irc.reply(
                #    "You have already given %i karma to %s" % (vote, recip))
                return

            forwards = data['forwards']
            forwards[agent][recip] = vote
            data['forwards'] = forwards

            backwards = data['backwards']
            backwards[recip][agent] = vote
            data['backwards'] = backwards

            # Count the number of karmas for old so-and-so.
            total = sum(data['backwards'][recip].values())
        finally:
            if data:
                data.close()

        fedmsg.publish(
            name="supybot.%s" % socket.gethostname(),
            modname="irc", topic="karma",
            msg={
                'agent': agent,
                'recipient': recip,
                'total': total,
                'vote': vote,
                'channel': channel,
                'line': line,
            },
        )

        url = self.registryValue('karma.url')
        irc.reply('Karma for %s changed to %r:  %s' % (recip, total, url))


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

    def pushduty(self, irc, msg, args):
        """

        Return the list of people who are on releng push duty right now.
        """

        def get_persons():
            for meeting in self._meetings_for('release-engineering'):
                yield meeting['meeting_name']

        persons = list(get_persons())

        url = "https://apps.fedoraproject.org/" + \
            "calendar/release-engineering/"

        if not persons:
            response = "Nobody is listed as being on push duty right now..."
            irc.reply(response.encode('utf-8'))
            irc.reply("- " + url.encode('utf-8'))
            return

        persons = ", ".join(persons)
        response = "The following people are on push duty: %s" % persons
        irc.reply(response.encode('utf-8'))
        irc.reply("- " + url.encode('utf-8'))
    pushduty = wrap(pushduty)

    def vacation(self, irc, msg, args):
        """

        Return the list of people who are on vacation right now.
        """

        def get_persons():
            for meeting in self._meetings_for('vacation'):
                for manager in meeting['meeting_manager']:
                    yield manager

        persons = list(get_persons())

        if not persons:
            response = "Nobody is listed as being on vacation right now..."
            irc.reply(response.encode('utf-8'))
            url = "https://apps.fedoraproject.org/calendar/vacation/"
            irc.reply("- " + url.encode('utf-8'))
            return

        persons = ", ".join(persons)
        response = "The following people are on vacation: %s" % persons
        irc.reply(response.encode('utf-8'))
        url = "https://apps.fedoraproject.org/calendar/vacation/"
        irc.reply("- " + url.encode('utf-8'))
    vacation = wrap(vacation)

    def nextmeetings(self, irc, msg, args):
        """
        Return the next meetings scheduled for any channel(s).
        """
        irc.reply('One moment, please...  Looking up the channel list.')
        url = 'https://apps.fedoraproject.org/calendar/api/locations/'
        locations = requests.get(url).json()['locations']
        meetings = sorted(chain(*[
            self._future_meetings(location)
            for location in locations
            if 'irc.freenode.net' in location
        ]), key=itemgetter(0))

        test, meetings = tee(meetings)
        try:
            test.next()
        except StopIteration:
            response = "There are no meetings scheduled at all."
            irc.reply(response.encode('utf-8'))
            return

        for date, meeting in islice(meetings, 0, 5):
            response = "In #%s is %s (starting %s)" % (
                meeting['meeting_location'].split('@')[0].strip(),
                meeting['meeting_name'],
                arrow.get(date).humanize(),
            )
            irc.reply(response.encode('utf-8'))
    nextmeetings = wrap(nextmeetings, [])

    def nextmeeting(self, irc, msg, args, channel):
        """<channel>

        Return the next meeting scheduled for a particular channel.
        """

        channel = channel.strip('#').split('@')[0]
        meetings = sorted(self._future_meetings(channel), key=itemgetter(0))

        test, meetings = tee(meetings)
        try:
            test.next()
        except StopIteration:
            response = "There are no meetings scheduled for #%s." % channel
            irc.reply(response.encode('utf-8'))
            return

        for date, meeting in islice(meetings, 0, 3):
            response = "In #%s is %s (starting %s)" % (
                channel,
                meeting['meeting_name'],
                arrow.get(date).humanize(),
            )
            irc.reply(response.encode('utf-8'))
        base = "https://apps.fedoraproject.org/calendar/location/"
        url = base + urllib.quote("%s@irc.freenode.net/" % channel)
        irc.reply("- " + url.encode('utf-8'))
    nextmeeting = wrap(nextmeeting, ['text'])

    @staticmethod
    def _future_meetings(location):
        if not location.endswith('@irc.freenode.net'):
            location = '%s@irc.freenode.net' % location
        meetings = Fedora._query_fedocal(location=location)
        now = datetime.datetime.utcnow()

        for meeting in meetings:
            string = "%s %s" % (meeting['meeting_date'],
                                meeting['meeting_time_start'])
            dt = datetime.datetime.strptime(string, "%Y-%m-%d %H:%M:%S")

            if now < dt:
                yield dt, meeting

    @staticmethod
    def _meetings_for(calendar):
        meetings = Fedora._query_fedocal(calendar=calendar)
        now = datetime.datetime.utcnow()

        for meeting in meetings:
            string = "%s %s" % (meeting['meeting_date'],
                                meeting['meeting_time_start'])
            start = datetime.datetime.strptime(string, "%Y-%m-%d %H:%M:%S")
            string = "%s %s" % (meeting['meeting_date_end'],
                                meeting['meeting_time_stop'])
            end = datetime.datetime.strptime(string, "%Y-%m-%d %H:%M:%S")

            if now >= start and now <= end:
                yield meeting

    @staticmethod
    def _query_fedocal(**kwargs):
        url = 'https://apps.fedoraproject.org/calendar/api/meetings'
        return requests.get(url, params=kwargs).json()['meetings']

    def badges(self, irc, msg, args, name):
        """<username>

        Return badges statistics about a user.
        """
        url = "https://badges.fedoraproject.org/user/" + name
        d = requests.get(url + "/json").json()

        if 'error' in d:
            response = d['error']
        else:
            template = "{name} has unlocked {n} Fedora Badges:  {url}"
            n = len(d['assertions'])
            response = template.format(name=name, url=url, n=n)

        irc.reply(response.encode('utf-8'))
    badges = wrap(badges, ['text'])

    def quote(self, irc, msg, args, arguments):
        """<SYMBOL> [daily, weekly, monthly, quarterly]

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

        if symbol not in symbols:
            response = "No such symbol %r.  Try one of %s"
            irc.reply((response % (symbol, key_fmt(symbols))).encode('utf-8'))
            return

        # Now, build another lookup of our various timeframes.
        frames = dict(
            daily=datetime.timedelta(days=1),
            weekly=datetime.timedelta(days=7),
            monthly=datetime.timedelta(days=30),
            quarterly=datetime.timedelta(days=91),
        )

        if frame not in frames:
            response = "No such timeframe %r.  Try one of %s"
            irc.reply((response % (frame, key_fmt(frames))).encode('utf-8'))
            return

        category = [symbols[symbol]]

        t2 = datetime.datetime.utcnow()
        t1 = t2 - frames[frame]
        t0 = t1 - frames[frame]

        # Count the number of messages between t0 and t1, and between t1 and t2
        query1 = dict(start=t0, end=t1, category=category)
        query2 = dict(start=t1, end=t2, category=category)

        # Do this async for superfast datagrepper queries.
        tpool = ThreadPool()
        batched_values = tpool.map(datagrepper_query, [
            dict(start=x, end=y, category=category)
            for x, y in Utils.daterange(t1, t2, SPARKLINE_RESOLUTION)
        ] + [query1, query2])

        count2 = batched_values.pop()
        count1 = batched_values.pop()

        # Just rename the results.  We'll use the rest for the sparkline.
        sparkline_values = batched_values

        yester_phrases = dict(
            daily="yesterday",
            weekly="the week preceding this one",
            monthly="the month preceding this one",
            quarterly="the 3 months preceding these past three months",
        )
        phrases = dict(
            daily="24 hours",
            weekly="week",
            monthly="month",
            quarterly="3 months",
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

        template = u"{sym}, {name} {sign}{percent:.2f}% over {phrase}"
        response = template.format(
            sym=symbol,
            name=symbols[symbol],
            sign=sign(percent),
            percent=abs(percent),
            phrase=yester_phrases[frame],
        )
        irc.reply(response.encode('utf-8'))

        # Now, make a graph out of it.
        sparkline = Utils.sparkline(sparkline_values)

        template = u"     {sparkline}  ⤆ over {phrase}"
        response = template.format(
            sym=symbol,
            sparkline=sparkline,
            phrase=phrases[frame]
        )
        irc.reply(response.encode('utf-8'))

        to_utc = lambda t: time.gmtime(time.mktime(t.timetuple()))
        # And a final line for "x-axis tics"
        t1_fmt = time.strftime("%H:%M UTC %m/%d", to_utc(t1))
        t2_fmt = time.strftime("%H:%M UTC %m/%d", to_utc(t2))
        padding = u" " * (SPARKLINE_RESOLUTION - len(t1_fmt) - 3)
        template = u"     ↑ {t1}{padding}↑ {t2}"
        response = template.format(t1=t1_fmt, t2=t2_fmt, padding=padding)
        irc.reply(response.encode('utf-8'))
    quote = wrap(quote, ['text'])


class Utils(object):
    """ Some handy utils for datagrepper visualization. """

    @classmethod
    def sparkline(cls, values):
        bar = u'▁▂▃▄▅▆▇█'
        barcount = len(bar) - 1
        values = map(float, values)
        mn, mx = min(values), max(values)
        extent = mx - mn

        if extent == 0:
            indices = [0 for n in values]
        else:
            indices = [int((n - mn) / extent * barcount) for n in values]

        unicode_sparkline = u''.join([bar[i] for i in indices])
        return unicode_sparkline

    @classmethod
    def daterange(cls, start, stop, steps):
        """ A generator for stepping through time. """
        delta = (stop - start) / steps
        current = start
        while current + delta <= stop:
            yield current, current + delta
            current += delta


Class = Fedora


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
