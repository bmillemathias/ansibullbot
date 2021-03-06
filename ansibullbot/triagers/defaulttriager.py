#!/usr/bin/python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import abc
import argparse
import json
import logging
import operator
import os
import sys
import time
from datetime import datetime
from pprint import pprint

from six.moves import input

# remember to pip install PyGithub, kids!
from github import Github

from jinja2 import Environment, FileSystemLoader

import ansibullbot.constants as C
from ansibullbot._pickle_compat import pickle_dump, pickle_load
from ansibullbot._text_compat import to_text
from ansibullbot.decorators.github import RateLimited
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from ansibullbot.utils.logs import set_logger

basepath = os.path.dirname(__file__).split('/')
libindex = basepath[::-1].index('ansibullbot')
libindex = (len(basepath) - 1) - libindex
basepath = '/'.join(basepath[0:libindex])
loader = FileSystemLoader(os.path.join(basepath, 'templates'))
environment = Environment(loader=loader, trim_blocks=True)


# https://github.com/ansible/ansibullbot/issues/1129
if 'equalto' not in environment.tests:
    environment.tests['equalto'] = operator.eq


class DefaultActions(object):
    def __init__(self):
        self.newlabel = []
        self.unlabel = []
        self.comments = []
        self.uncomment = []
        self.assign = []
        self.unassign = []
        self.close = False
        self.open = False
        self.merge = False

    def count(self):
        """ Return the number of actions that are to be performed """
        count = 0
        for value in vars(self).values():
            if value:
                if isinstance(value, bool):
                    count += 1
                else:
                    count += len(value)

        return count


class DefaultTriager(object):
    """
    How to use:
    1. Create a new class which inherits from DefaultTriager
    2. Implement 'Triager.run(self)' method:
        - iterate over issues/pull requests
        - for each issue
        1. create 'actions = DefaultActions()'
        2. define which action(s) should be done updating 'actions' instance
        3. call parent 'apply_actions' methods: 'DefaultTriager.apply_actions(iw, actions)'
    3. Run:
    def main():
        Triager().start()
    """
    ITERATION = 0
    debug = False
    cachedir_base = None
    BOTNAMES = C.DEFAULT_BOT_NAMES

    def __init__(self, args=None):
        pass

    @classmethod
    def create_parser(cls):
        """Creates an argument parser

        Returns:
            A argparse.ArgumentParser object
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--cachedir", type=str, dest='cachedir_base',
                            default='~/.ansibullbot/cache')
        parser.add_argument("--logfile", type=str,
                            default='/var/log/ansibullbot.log',
                            help="Send logging to this file")
        parser.add_argument("--daemonize", action="store_true",
                            help="run in a continuos loop")
        parser.add_argument("--daemonize_interval", type=int, default=(30 * 60),
                            help="seconds to sleep between loop iterations")
        parser.add_argument("--debug", "-d", action="store_true",
                            help="Debug output")
        parser.add_argument("--verbose", "-v", action="store_true",
                            help="Verbose output")
        parser.add_argument("--dry-run", "-n", action="store_true",
                            help="Don't make any changes")
        parser.add_argument("--force", "-f", action="store_true",
                            help="Do not ask questions")
        parser.add_argument("--pause", "-p", action="store_true", dest="always_pause",
                            help="Always pause between prs|issues")
        parser.add_argument("--force_rate_limit", action="store_true",
                            help="debug: force the rate limit")
        # useful for debugging
        parser.add_argument("--dump_actions", action="store_true",
                            help="serialize the actions to disk [/tmp/actions]")
        parser.add_argument("--botmetafile", type=str,
                            default=None,
                            help="Use this filepath for botmeta instead of from the repo")
        return parser

    def set_logger(self):
        set_logger(debug=self.debug, logfile=self.logfile)

    def start(self):

        if self.force_rate_limit:
            logging.warning('attempting to trigger rate limit')
            self.trigger_rate_limit()
            return

        if self.daemonize:
            logging.info('starting daemonize loop')
            self.loop()
        else:
            logging.info('starting single run')
            self.run()
        logging.info('stopping bot')

    @RateLimited
    def _connect(self):
        """Connects to GitHub's API"""
        if self.github_token:
            return Github(base_url=self.github_url, login_or_token=self.github_token)
        else:
            return Github(
                base_url=self.github_url,
                login_or_token=self.github_user,
                password=self.github_pass
            )

    def is_pr(self, issue):
        if '/pull/' in issue.html_url:
            return True
        else:
            return False

    def is_issue(self, issue):
        return not self.is_pr(issue)

    @RateLimited
    def get_members(self, organization):
        """Get members of an organization

        Args:
            organization: name of the organization

        Returns:
            A list of GitHub login belonging to the organization
        """
        members = []
        update = False
        write_cache = False
        now = self.get_current_time()
        gh_org = self._connect().get_organization(organization)

        cachedir = os.path.join(self.cachedir_base, organization)
        if not os.path.isdir(cachedir):
            os.makedirs(cachedir)

        cachefile = os.path.join(cachedir, 'members.pickle')

        if os.path.isfile(cachefile):
            with open(cachefile, 'rb') as f:
                mdata = pickle_load(f)
            members = mdata[1]
            if mdata[0] < gh_org.updated_at:
                update = True
        else:
            update = True
            write_cache = True

        if update:
            members = gh_org.get_members()
            members = [x.login for x in members]

        # save the data
        if write_cache:
            mdata = [now, members]
            with open(cachefile, 'wb') as f:
                pickle_dump(mdata, f)

        return members

    @RateLimited
    def get_core_team(self, organization, teams):
        """Get members of the core team

        Args:
            organization: name of the teams' organization
            teams: list of teams that compose the project core team

        Returns:
            A list of GitHub login belonging to teams
        """
        members = set()

        conn = self._connect()
        gh_org = conn.get_organization(organization)
        for team in gh_org.get_teams():
            if team.name in teams:
                for member in team.get_members():
                    members.add(member.login)

        return sorted(members)

    #@RateLimited
    def get_valid_labels(self, repo):

        # use the repo wrapper to enable caching+updating
        if not self.ghw:
            self.gh = self._connect()
            self.ghw = GithubWrapper(self.gh)

        rw = self.ghw.get_repo(repo)
        vlabels = []
        for vl in rw.labels:
            vlabels.append(vl.name)

        return vlabels

    def loop(self):
        '''Call the run method in a defined interval'''
        while True:
            self.run()
            self.ITERATION += 1
            interval = self.daemonize_interval
            logging.info('sleep %ss (%sm)' % (interval, interval / 60))
            time.sleep(interval)

    @abc.abstractmethod
    def run(self):
        pass

    def get_current_time(self):
        return datetime.utcnow()

    def render_boilerplate(self, tvars, boilerplate=None):
        template = environment.get_template('%s.j2' % boilerplate)
        comment = template.render(**tvars)
        return comment

    def apply_actions(self, iw, actions):
        action_meta = {'REDO': False}

        if actions.count() > 0:
            if self.dump_actions:
                self.dump_action_dict(iw, actions)

            if self.dry_run:
                print("Dry-run specified, skipping execution of actions")
            else:
                if self.force:
                    print("Running actions non-interactive as you forced.")
                    self.execute_actions(iw, actions)
                    return action_meta
                cont = input("Take recommended actions (y/N/a/R/DEBUG)? ")
                if cont in ('a', 'A'):
                    sys.exit(0)
                if cont in ('Y', 'y'):
                    self.execute_actions(iw, actions)
                if cont in ('r', 'R'):
                    action_meta['REDO'] = True
                if cont == 'DEBUG':
                    # put the user into a breakpoint to do live debug
                    action_meta['REDO'] = True
                    import epdb; epdb.st()
        elif self.always_pause:
            print("Skipping, but pause.")
            cont = input("Continue (Y/n/a/R/DEBUG)? ")
            if cont in ('a', 'A', 'n', 'N'):
                sys.exit(0)
            elif cont in ('r', 'R'):
                action_meta['REDO'] = True
            elif cont == 'DEBUG':
                # put the user into a breakpoint to do live debug
                import epdb; epdb.st()
                action_meta['REDO'] = True
        else:
            print("Skipping.")

        # let the upper level code redo this issue
        return action_meta

    def execute_actions(self, iw, actions):
        """Turns the actions into API calls"""

        for commentid in actions.uncomment:
            iw.remove_comment_by_id(commentid)

        for comment in actions.comments:
            logging.info("acton: comment - " + comment)
            iw.add_comment(comment=comment)

        if actions.close:
            # https://github.com/PyGithub/PyGithub/blob/master/github/Issue.py#L263
            logging.info('action: close')
            iw.instance.edit(state='closed')

        else:

            for unlabel in actions.unlabel:
                logging.info('action: unlabel - ' + unlabel)
                iw.remove_label(label=unlabel)
            for newlabel in actions.newlabel:
                logging.info('action: label - ' + newlabel)
                iw.add_label(label=newlabel)

            for user in actions.assign:
                logging.info('action: assign - ' + user)
                iw.assign_user(user)

            for user in actions.unassign:
                logging.info('action: unassign - ' + user)
                iw.unassign_user(user)

            if actions.merge:
                iw.merge()

        # FIXME why?
        self.build_history(iw)

    #@RateLimited
    def is_pr_merged(self, number, repo):
        '''Check if a PR# has been merged or not'''

        if number is None:
            if C.DEFAULT_BREAKPOINTS:
                logging.error('breakpoint!')
                import epdb; epdb.st()
            raise Exception('Can not check merge state on the number: None')

        merged = False
        pr = None
        try:
            pr = repo.get_pullrequest(number)
        except Exception as e:
            print(e)
        if pr:
            try:
                merged = pr.merged
            except Exception as e:
                logging.debug(e)
                if C.DEFAULT_BREAKPOINTS:
                    logging.error('breakpoint!')
                    import epdb; epdb.st()
        return merged

    def trigger_rate_limit(self):
        '''Repeatedly make calls to exhaust rate limit'''

        self.gh = self._connect()
        self.ghw = GithubWrapper(self.gh)

        while True:
            cachedir = os.path.join(self.cachedir_base, self.repo)
            thisrepo = self.ghw.get_repo(self.repo, verbose=False)
            issues = thisrepo.repo.get_issues()
            rl = thisrepo.get_rate_limit()
            pprint(rl)

            for issue in issues:
                iw = IssueWrapper(
                        github=self.ghw,
                        repo=thisrepo,
                        issue=issue,
                        cachedir=cachedir
                )
                iw.history
                rl = thisrepo.get_rate_limit()
                pprint(rl)

    def dump_action_dict(self, issue, actions):
        '''Serialize the action dict to disk for quick(er) debugging'''
        fn = os.path.join(u'/tmp', u'actions', issue.repo_full_name, to_text(issue.number) + u'.json')
        dn = os.path.dirname(fn)
        if not os.path.isdir(dn):
            os.makedirs(dn)

        logging.info('dumping {}'.format(fn))
        with open(fn, 'wb') as f:
            f.write(json.dumps(actions, indent=2, sort_keys=True))
