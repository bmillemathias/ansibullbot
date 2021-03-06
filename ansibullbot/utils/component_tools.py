#!/usr/bin/env python

import copy
import datetime
import json
import logging
import os
import re

from collections import OrderedDict

import six

from Levenshtein import jaro_winkler

from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.utils.extractors import ModuleExtractor
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command

from ansibullbot.utils.galaxy import GalaxyQueryTool


MODULES_FLATTEN_MAP = {
    'lib/ansible/modules/inventory/add_host.py': 'lib/ansible/modules/add_host.py',
    'lib/ansible/modules/packaging/os/apt.py': 'lib/ansible/modules/apt.py',
    'lib/ansible/modules/packaging/os/apt_key.py': 'lib/ansible/modules/apt_key.py',
    'lib/ansible/modules/packaging/os/apt_repository.py': 'lib/ansible/modules/apt_repository.py',
    'lib/ansible/modules/files/assemble.py': 'lib/ansible/modules/assemble.py',
    'lib/ansible/modules/utilities/logic/assert.py': 'lib/ansible/modules/assert.py',
    'lib/ansible/modules/utilities/logic/async_status.py': 'lib/ansible/modules/async_status.py',
    'lib/ansible/modules/utilities/logic/async_wrapper.py': 'lib/ansible/modules/async_wrapper.py',
    'lib/ansible/modules/files/blockinfile.py': 'lib/ansible/modules/blockinfile.py',
    'lib/ansible/modules/commands/command.py': 'lib/ansible/modules/command.py',
    'lib/ansible/modules/files/copy.py': 'lib/ansible/modules/copy.py',
    'lib/ansible/modules/system/cron.py': 'lib/ansible/modules/cron.py',
    'lib/ansible/modules/system/debconf.py': 'lib/ansible/modules/debconf.py',
    'lib/ansible/modules/utilities/logic/debug.py': 'lib/ansible/modules/debug.py',
    'lib/ansible/modules/packaging/os/dnf.py': 'lib/ansible/modules/dnf.py',
    'lib/ansible/modules/packaging/os/dpkg_selections.py': 'lib/ansible/modules/dpkg_selections.py',
    'lib/ansible/modules/commands/expect.py': 'lib/ansible/modules/expect.py',
    'lib/ansible/modules/utilities/logic/fail.py': 'lib/ansible/modules/fail.py',
    'lib/ansible/modules/files/fetch.py': 'lib/ansible/modules/fetch.py',
    'lib/ansible/modules/files/file.py': 'lib/ansible/modules/file.py',
    'lib/ansible/modules/files/find.py': 'lib/ansible/modules/find.py',
    'lib/ansible/modules/system/gather_facts.py': 'lib/ansible/modules/gather_facts.py',
    'lib/ansible/modules/net_tools/basics/get_url.py': 'lib/ansible/modules/get_url.py',
    'lib/ansible/modules/system/getent.py': 'lib/ansible/modules/getent.py',
    'lib/ansible/modules/source_control/git.py': 'lib/ansible/modules/git.py',
    'lib/ansible/modules/system/group.py': 'lib/ansible/modules/group.py',
    'lib/ansible/modules/inventory/group_by.py': 'lib/ansible/modules/group_by.py',
    'lib/ansible/modules/system/hostname.py': 'lib/ansible/modules/hostname.py',
    'lib/ansible/modules/utilities/logic/import_playbook.py': 'lib/ansible/modules/import_playbook.py',
    'lib/ansible/modules/utilities/logic/import_role.py': 'lib/ansible/modules/import_role.py',
    'lib/ansible/modules/utilities/logic/import_tasks.py': 'lib/ansible/modules/import_tasks.py',
    'lib/ansible/modules/utilities/logic/include.py': 'lib/ansible/modules/include.py',
    'lib/ansible/modules/utilities/logic/include_role.py': 'lib/ansible/modules/include_role.py',
    'lib/ansible/modules/utilities/logic/include_tasks.py': 'lib/ansible/modules/include_tasks.py',
    'lib/ansible/modules/utilities/logic/include_vars.py': 'lib/ansible/modules/include_vars.py',
    'lib/ansible/modules/system/iptables.py': 'lib/ansible/modules/iptables.py',
    'lib/ansible/modules/system/known_hosts.py': 'lib/ansible/modules/known_hosts.py',
    'lib/ansible/modules/files/lineinfile.py': 'lib/ansible/modules/lineinfile.py',
    'lib/ansible/modules/utilities/helper/meta.py': 'lib/ansible/modules/meta.py',
    'lib/ansible/modules/packaging/os/package.py': 'lib/ansible/modules/package.py',
    'lib/ansible/modules/packaging/os/package_facts.py': 'lib/ansible/modules/package_facts.py',
    'lib/ansible/modules/utilities/logic/pause.py': 'lib/ansible/modules/pause.py',
    'lib/ansible/modules/system/ping.py': 'lib/ansible/modules/ping.py',
    'lib/ansible/modules/packaging/language/pip.py': 'lib/ansible/modules/pip.py',
    'lib/ansible/modules/commands/raw.py': 'lib/ansible/modules/raw.py',
    'lib/ansible/modules/system/reboot.py': 'lib/ansible/modules/reboot.py',
    'lib/ansible/modules/files/replace.py': 'lib/ansible/modules/replace.py',
    'lib/ansible/modules/packaging/os/rpm_key.py': 'lib/ansible/modules/rpm_key.py',
    'lib/ansible/modules/commands/script.py': 'lib/ansible/modules/script.py',
    'lib/ansible/modules/system/service.py': 'lib/ansible/modules/service.py',
    'lib/ansible/modules/system/service_facts.py': 'lib/ansible/modules/service_facts.py',
    'lib/ansible/modules/utilities/logic/set_fact.py': 'lib/ansible/modules/set_fact.py',
    'lib/ansible/modules/utilities/logic/set_stats.py': 'lib/ansible/modules/set_stats.py',
    'lib/ansible/modules/system/setup.py': 'lib/ansible/modules/setup.py',
    'lib/ansible/modules/commands/shell.py': 'lib/ansible/modules/shell.py',
    'lib/ansible/modules/net_tools/basics/slurp.py': 'lib/ansible/modules/slurp.py',
    'lib/ansible/modules/files/stat.py': 'lib/ansible/modules/stat.py',
    'lib/ansible/modules/source_control/subversion.py': 'lib/ansible/modules/subversion.py',
    'lib/ansible/modules/system/systemd.py': 'lib/ansible/modules/systemd.py',
    'lib/ansible/modules/system/sysvinit.py': 'lib/ansible/modules/sysvinit.py',
    'lib/ansible/modules/files/tempfile.py': 'lib/ansible/modules/tempfile.py',
    'lib/ansible/modules/files/template.py': 'lib/ansible/modules/template.py',
    'lib/ansible/modules/files/unarchive.py': 'lib/ansible/modules/unarchive.py',
    'lib/ansible/modules/net_tools/basics/uri.py': 'lib/ansible/modules/uri.py',
    'lib/ansible/modules/system/user.py': 'lib/ansible/modules/user.py',
    'lib/ansible/modules/utilities/logic/wait_for.py': 'lib/ansible/modules/wait_for.py',
    'lib/ansible/modules/utilities/logic/wait_for_connection.py': 'lib/ansible/modules/wait_for_connection.py',
    'lib/ansible/modules/packaging/os/yum.py': 'lib/ansible/modules/yum.py',
    'lib/ansible/modules/packaging/os/yum_repository.py': 'lib/ansible/modules/yum_repository.py',
}


def make_prefixes(filename):
    # make a byte by byte list of prefixes for this fp
    indexes = range(0, len(filename) + 1)
    indexes = [1-x for x in indexes]
    indexes = [x for x in indexes if x < 0]
    indexes = [None] + indexes
    prefixes = [filename[:x] for x in indexes]
    return prefixes


class AnsibleComponentMatcher(object):

    botmeta = {}
    GALAXY_FILES = {}
    GALAXY_MANIFESTS = {}
    INDEX = {}
    REPO = u'https://github.com/ansible/ansible'
    STOPWORDS = [u'ansible', u'core', u'plugin']
    STOPCHARS = [u'"', "'", u'(', u')', u'?', u'*', u'`', u',', u':', u'?', u'-']
    BLACKLIST = [u'new module', u'new modules']
    FILE_NAMES = []
    MODULES = OrderedDict()
    MODULE_NAMES = []
    MODULE_NAMESPACE_DIRECTORIES = []
    PREVIOUS_FILES = []

    # FIXME: THESE NEED TO GO INTO botmeta
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        u'N/A': u'lib/ansible/cli/__init__.py',
        u'n/a': u'lib/ansible/cli/__init__.py',
        u'all': u'lib/ansible/cli/__init__.py',
        u'ansiballz': u'lib/ansible/executor/module_common.py',
        u'ansible-console': u'lib/ansible/cli/console.py',
        u'ansible-galaxy': u'lib/ansible/galaxy',
        u'ansible-inventory': u'lib/ansible/cli/inventory.py',
        u'ansible logging': u'lib/ansible/plugins/callback/default.py',
        u'ansible-playbook': u'lib/ansible/playbook',
        u'ansible playbook': u'lib/ansible/playbook',
        u'ansible playbooks': u'lib/ansible/playbook',
        u'ansible-pull': u'lib/ansible/cli/pull.py',
        u'ansible-vault': u'lib/ansible/parsing/vault',
        u'ansible-vault edit': u'lib/ansible/parsing/vault',
        u'ansible-vault show': u'lib/ansible/parsing/vault',
        u'ansible-vault decrypt': u'lib/ansible/parsing/vault',
        u'ansible-vault encrypt': u'lib/ansible/parsing/vault',
        u'async': u'lib/ansible/modules/utilities/logic/async_wrapper.py',
        u'become': u'lib/ansible/playbook/become.py',
        u'block': u'lib/ansible/playbook/block.py',
        u'blocks': u'lib/ansible/playbook/block.py',
        u'bot': u'docs/docsite/rst/community/development_process.rst',
        u'callback plugin': u'lib/ansible/plugins/callback',
        u'callback plugins': u'lib/ansible/plugins/callback',
        u'callbacks': u'lib/ansible/plugins/callback/__init__.py',
        u'cli': u'lib/ansible/cli/__init__.py',
        u'conditional': u'lib/ansible/playbook/conditional.py',
        u'core': 'lib/ansible/cli/__init__.py',
        u'docs': u'docs/docsite/README.md',
        u'docs.ansible.com': u'docs/docsite/README.md',
        u'delegate_to': u'lib/ansible/playbook/task.py',
        u'ec2.py dynamic inventory script': 'contrib/inventory/ec2.py',
        u'ec2 dynamic inventory script': 'contrib/inventory/ec2.py',
        u'ec2 inventory script': 'contrib/inventory/ec2.py',
        u'facts': u'lib/ansible/module_utils/facts',
        u'galaxy': u'lib/ansible/galaxy',
        u'groupvars': u'lib/ansible/vars/hostvars.py',
        u'group vars': u'lib/ansible/vars/hostvars.py',
        u'handlers': u'lib/ansible/playbook/handler.py',
        u'hostvars': u'lib/ansible/vars/hostvars.py',
        u'host vars': u'lib/ansible/vars/hostvars.py',
        u'integration tests': u'test/integration',
        u'inventory script': u'contrib/inventory',
        u'jinja2 template system': u'lib/ansible/template',
        u'logging': u'lib/ansible/plugins/callback/default.py',
        u'module_utils': u'lib/ansible/module_utils',
        u'multiple modules': None,
        u'new module(s) request': None,
        u'new modules request': None,
        u'new module request': None,
        u'new module': None,
        u'network_cli': u'lib/ansible/plugins/connection/network_cli.py',
        u'network_cli.py': u'lib/ansible/plugins/connection/network_cli.py',
        u'network modules': u'lib/ansible/modules/network',
        u'nxos': u'lib/ansible/modules/network/nxos/__init__.py',
        u'paramiko': u'lib/ansible/plugins/connection/paramiko_ssh.py',
        u'redis fact caching': u'lib/ansible/plugins/cache/redis.py',
        u'role': u'lib/ansible/playbook/role',
        u'roles': u'lib/ansible/playbook/role',
        u'ssh': u'lib/ansible/plugins/connection/ssh.py',
        u'ssh authentication': u'lib/ansible/plugins/connection/ssh.py',
        u'setup / facts': u'lib/ansible/modules/system/setup.py',
        u'setup': u'lib/ansible/modules/system/setup.py',
        u'task executor': u'lib/ansible/executor/task_executor.py',
        u'testing': u'test/',
        #u'validate-modules': u'test/sanity/validate-modules',
        u'validate-modules': u'test/sanity/code-smell',
        u'vault': u'lib/ansible/parsing/vault',
        u'vault edit': u'lib/ansible/parsing/vault',
        u'vault documentation': u'lib/ansible/parsing/vault',
        u'with_items': u'lib/ansible/playbook/loop_control.py',
        u'windows modules': u'lib/ansible/modules/windows',
        u'winrm': u'lib/ansible/plugins/connection/winrm.py'
    }

    def __init__(self, gitrepo=None, botmeta=None, usecache=False, cachedir=None, commit=None, email_cache=None, use_galaxy=False):
        self.usecache = usecache
        self.cachedir = cachedir
        self.use_galaxy = use_galaxy
        self.botmeta = botmeta if botmeta else {u'files': {}}
        self.email_cache = email_cache
        self.commit = commit

        if gitrepo:
            self.gitrepo = gitrepo
        else:
            self.gitrepo = GitRepoWrapper(cachedir=cachedir, repo=self.REPO, commit=self.commit)

        # we need to query galaxy for a few things ...
        if not use_galaxy:
            self.GQT = None
        else:
            self.GQT = GalaxyQueryTool(cachedir=self.cachedir)

        self.strategy = None
        self.strategies = []

        self.indexed_at = False
        self.updated_at = None
        self.update(refresh_botmeta=False)

    def update(self, email_cache=None, refresh_botmeta=True, usecache=False, use_galaxy=True, botmeta=None):
        if botmeta is not None:
            self.botmeta = botmeta
        if self.GQT is not None and use_galaxy:
            self.GQT.update()
        if email_cache:
            self.email_cache = email_cache
        self.index_files()
        self.indexed_at = datetime.datetime.now()
        self.cache_keywords()
        self.updated_at = datetime.datetime.now()

    def get_module_meta(self, checkoutdir, filename1, filename2):

        if self.cachedir:
            cdir = os.path.join(self.cachedir, 'module_extractor_cache')
        else:
            cdir = '/tmp/ansibot_module_extractor_cache'
        if not os.path.exists(cdir) and self.usecache:
            os.makedirs(cdir)
        cfile = os.path.join(cdir, '%s.json' % os.path.basename(filename1))

        bmeta = None
        if not os.path.exists(cfile) or not self.usecache:
            bmeta = {}
            efile = os.path.join(checkoutdir, filename1)
            if not os.path.exists(efile):
                fdata = self.gitrepo.get_file_content(filename1, follow=True)
                ME = ModuleExtractor(None, filedata=fdata, email_cache=self.email_cache)
            else:
                ME = ModuleExtractor(os.path.join(checkoutdir, filename1), email_cache=self.email_cache)
            if filename1 not in self.botmeta[u'files']:
                bmeta = {
                    u'deprecated': os.path.basename(filename1).startswith(u'_'),
                    u'labels': os.path.dirname(filename1).split(u'/'),
                    u'authors': ME.authors,
                    u'maintainers': ME.authors,
                    u'maintainers_keys': [],
                    u'notified': ME.authors,
                    u'ignored': [],
                    u'support': ME.metadata.get(u'supported_by', u'community'),
                    u'metadata': ME.metadata.copy()
                }
            else:
                bmeta = self.botmeta[u'files'][filename1].copy()
                bmeta[u'metadata'] = ME.metadata.copy()
                if u'notified' not in bmeta:
                    bmeta[u'notified'] = []
                if u'maintainers' not in bmeta:
                    bmeta[u'maintainers'] = []
                if not bmeta.get(u'supported_by'):
                    bmeta[u'supported_by'] = ME.metadata.get(u'supported_by', u'community')
                if u'authors' not in bmeta:
                    bmeta[u'authors'] = []
                for x in ME.authors:
                    if x not in bmeta[u'authors']:
                        bmeta[u'authors'].append(x)
                    if x not in bmeta[u'maintainers']:
                        bmeta[u'maintainers'].append(x)
                    if x not in bmeta[u'notified']:
                        bmeta[u'notified'].append(x)
                if not bmeta.get(u'labels'):
                    bmeta[u'labels'] = os.path.dirname(filename1).split(u'/')
                bmeta[u'deprecated'] = os.path.basename(filename1).startswith(u'_')

            # clean out the ignorees
            if u'ignored' in bmeta:
                for ignoree in bmeta[u'ignored']:
                    for thiskey in [u'maintainers', u'notified']:
                        while ignoree in bmeta[thiskey]:
                            bmeta[thiskey].remove(ignoree)

            if self.usecache:
                with open(cfile, 'w') as f:
                    f.write(json.dumps(bmeta))

        if bmeta is None and self.usecache:
            with open(cfile, 'r') as f:
                bmeta = json.loads(f.read())

        return bmeta

    def index_files(self):
        self.MODULES = OrderedDict()
        self.MODULE_NAMES = []
        self.MODULE_NAMESPACE_DIRECTORIES = []

        for fn in self.gitrepo.module_files:
            if self.gitrepo.isdir(fn):
                continue
            if not self.gitrepo.exists(fn):
                continue
            mname = os.path.basename(fn)
            mname = mname.replace(u'.py', u'').replace(u'.ps1', u'')
            if mname.startswith(u'__'):
                continue
            mdata = {
                u'name': mname,
                u'repo_filename': fn,
                u'filename': fn
            }
            if fn not in self.MODULES:
                self.MODULES[fn] = mdata.copy()
            else:
                self.MODULES[fn].update(mdata)

        self.MODULE_NAMESPACE_DIRECTORIES = (os.path.dirname(x) for x in self.gitrepo.module_files)
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))

        # make a list of names by enumerating the files
        self.MODULE_NAMES = (os.path.basename(x) for x in self.gitrepo.module_files)
        self.MODULE_NAMES = (x for x in self.MODULE_NAMES if x.endswith((u'.py', u'.ps1')))
        self.MODULE_NAMES = (x.replace(u'.ps1', u'').replace(u'.py', u'') for x in self.MODULE_NAMES)
        self.MODULE_NAMES = (x for x in self.MODULE_NAMES if not x.startswith(u'__'))
        self.MODULE_NAMES = sorted(set(self.MODULE_NAMES))

        # append module names from botmeta
        bmodules = [x for x in self.botmeta[u'files'] if x.startswith(u'lib/ansible/modules')]
        bmodules = [x for x in bmodules if x.endswith(u'.py') or x.endswith(u'.ps1')]
        bmodules = [x for x in bmodules if u'__init__' not in x]
        for bmodule in bmodules:
            mn = os.path.basename(bmodule).replace(u'.py', u'').replace(u'.ps1', u'')
            mn = mn.lstrip('_')
            if mn not in self.MODULE_NAMES:
                self.MODULE_NAMES.append(mn)
            if bmodule not in self.MODULES:
                self.MODULES[bmodule] = {
                    'filename': bmodule,
                    'repo_filename': bmodule,
                    'name': mn
                }

        # make a list of names by calling ansible-doc
        checkoutdir = self.gitrepo.checkoutdir
        checkoutdir = os.path.abspath(checkoutdir)
        cmd = u'. {}/hacking/env-setup; ansible-doc -t module -F'.format(checkoutdir)
        logging.debug(cmd)
        (rc, so, se) = run_command(cmd, cwd=checkoutdir)
        if rc != 0:
            raise Exception("'ansible-doc' command failed (%s, %s %s)" % (rc, so, se))
        lines = to_text(so).split(u'\n')
        for line in lines:

            # compat for macos tmpdirs
            if u' /private' in line:
                line = line.replace(u' /private', u'', 1)

            parts = line.split()
            parts = [x.strip() for x in parts]

            if len(parts) != 2 or checkoutdir not in line:
                continue

            mname = parts[0]
            if mname not in self.MODULE_NAMES:
                self.MODULE_NAMES.append(mname)

            fpath = parts[1]
            fpath = fpath.replace(checkoutdir + u'/', u'')

            if fpath not in self.MODULES:
                self.MODULES[fpath] = {
                    u'name': mname,
                    u'repo_filename': fpath,
                    u'filename': fpath
                }

        _modules = self.MODULES.copy()
        for k, v in _modules.items():
            kparts = os.path.splitext(k)
            if kparts[-1] == u'.ps1':
                _k = kparts[0] + u'.py'
                checkpath = os.path.join(checkoutdir, _k)
                if not os.path.isfile(checkpath):
                    _k = k
            else:
                _k = k
            logging.debug('extract %s' % k)
            fmeta = self.get_module_meta(checkoutdir, k, _k)
            if k in self.botmeta[u'files']:
                self.botmeta['files'][k].update(fmeta)
            else:
                self.botmeta['files'][k] = copy.deepcopy(fmeta)
            self.MODULES[k].update(fmeta)

    def cache_keywords(self):
        for k, v in self.botmeta[u'files'].items():
            if not v.get(u'keywords'):
                continue
            for kw in v[u'keywords']:
                if kw not in self.KEYWORDS:
                    self.KEYWORDS[kw] = k

    def clean_body(self, body, internal=False):
        body = body.lower()
        body = body.strip()
        for SC in self.STOPCHARS:
            if body.startswith(SC):
                body = body.lstrip(SC)
                body = body.strip()
            if body.endswith(SC):
                body = body.rstrip(SC)
                body = body.strip()
            if internal and SC in body:
                body = body.replace(SC, u'')
                body = body.strip()
        body = body.strip()
        return body

    def match(self, issuewrapper):
        iw = issuewrapper
        matchdata = self.match_components(
            iw.title,
            iw.body,
            iw.template_data.get(u'component_raw'),
            files=iw.files
        )
        return matchdata

    def match_components(self, title, body, component, files=None):
        """Make a list of matching files with metadata"""

        self.strategy = None
        self.strategies = []
        matched_filenames = None

        #import epdb; epdb.st()

        # No matching necessary for PRs, but should provide consistent api
        if files:
            matched_filenames = files[:]
        elif not component or component is None:
            return []
        elif ' ' not in component and '\n' not in component and component.startswith('lib/') and self.gitrepo.existed(component):
            matched_filenames = [component]
        else:
            matched_filenames = []
            if component is None:
                return matched_filenames

            logging.debug(u'match "{}"'.format(component))

            delimiters = [u'\n', u',', u' + ', u' & ']
            delimited = False
            for delimiter in delimiters:
                if delimiter in component:
                    delimited = True
                    components = component.split(delimiter)
                    for _component in components:
                        _matches = self._match_component(title, body, _component)
                        self.strategies.append(self.strategy)

                        # bypass for blacklist
                        if None in _matches:
                            _matches = []

                        matched_filenames += _matches

                    # do not process any more delimiters
                    break

            if not delimited:
                matched_filenames += self._match_component(title, body, component)
                self.strategies.append(self.strategy)

                # bypass for blacklist
                if None in matched_filenames:
                    return []

            # reduce subpaths
            if matched_filenames:
                matched_filenames = self.reduce_filepaths(matched_filenames)

        # mitigate flattening of the modules directory
        if matched_filenames:
            matched_filenames = [MODULES_FLATTEN_MAP.get(fn, fn) for fn in matched_filenames]

        # create metadata for each matched file
        component_matches = []
        matched_filenames = sorted(set(matched_filenames))
        for fn in matched_filenames:
            component_matches.append(self.get_meta_for_file(fn))
            if self.gitrepo.exists(fn):
                component_matches[-1]['exists'] = True
                component_matches[-1]['existed'] = True
            elif self.gitrepo.existed(fn):
                component_matches[-1]['exists'] = False
                component_matches[-1]['existed'] = True
            else:
                component_matches[-1]['exists'] = False
                component_matches[-1]['existed'] = False

        return component_matches

    def search_ecosystem(self, component):

        # never search collections for files that still exist
        if self.gitrepo.exists(component):
            return []

        if component.endswith('/') and self.gitrepo.exists(component.rstrip('/')):
            return []

        matched_filenames = []

        '''
        # botmeta -should- be the source of truth, but it's proven not to be ...
        if not matched_filenames:
            matched_filenames += self.search_by_botmeta_migrated_to(component)
        '''

        if self.GQT is not None:
            # see what is actually in galaxy ...
            matched_filenames += self.GQT.search_galaxy(component)

            # fallback to searching for migrated directories ...
            if not matched_filenames and component.startswith('lib/ansible/modules'):
                matched_filenames += self.GQT.fuzzy_search_galaxy(component)

        return matched_filenames

    def _match_component(self, title, body, component):
        """Find matches for a single line"""

        if not component:
            return []

        matched_filenames = []

        # sometimes we get urls ...
        #   https://github.com/ansible/ansible/issues/68553
        #   https//github.com/ansible/ansible/blob/devel/docs/docsite/rst/user_guide...
        if component.startswith('http'):
            if '/blob/' in component:
                # chop off the branch+path
                component = component.split('/blob/')[-1]
                # chop off the path
                component = component.split('/', 1)[-1]

        # don't neeed to match if it's a known file ...
        if self.gitrepo.exists(component.strip()):
            return [component.strip()]

        # context sets the path prefix to narrow the search window
        if u'module_util' in title.lower() or u'module_util' in component.lower():
            context = u'lib/ansible/module_utils'
        elif u'module util' in title.lower() or u'module util' in component.lower():
            context = u'lib/ansible/module_utils'
        elif u'module' in title.lower() or u'module' in component.lower():
            context = u'lib/ansible/modules'
        elif u'dynamic inventory' in title.lower() or u'dynamic inventory' in component.lower():
            context = u'contrib/inventory'
        elif u'inventory script' in title.lower() or u'inventory script' in component.lower():
            context = u'contrib/inventory'
        elif u'inventory plugin' in title.lower() or u'inventory plugin' in component.lower():
            context = u'lib/ansible/plugins/inventory'
        elif u'integration test' in title.lower() or u'integration test' in component.lower():
            context = u'test/integration/targets'
            component = component.replace('integration test', '').strip()
        else:
            context = None

        if component not in self.STOPWORDS and component not in self.STOPCHARS:

            '''
            if not matched_filenames:
                matched_filenames += self.search_by_botmeta_migrated_to(component)
                if matched_filenames:
                    self.strategy = u'search_by_botmeta_migrated_to'

            if not matched_filenames:
                matched_filenames += self.search_by_galaxy(component)
                if matched_filenames:
                    self.strategy = u'search_by_galaxy'
            '''

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=True)
                if matched_filenames:
                    self.strategy = u'search_by_keywords'

            if not matched_filenames:
                matched_filenames += self.search_by_module_name(component)
                if matched_filenames:
                    self.strategy = u'search_by_module_name'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_module_globs(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_module_globs'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_modules(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_modules'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_generic(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_generic'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_urls(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_urls'

            if not matched_filenames:
                matched_filenames += self.search_by_tracebacks(component)
                if matched_filenames:
                    self.strategy = u'search_by_tracebacks'

            if not matched_filenames:
                matched_filenames += self.search_by_filepath(component, context=context)
                if matched_filenames:
                    self.strategy = u'search_by_filepath'
                if not matched_filenames:
                    matched_filenames += self.search_by_filepath(component, partial=True)
                    if matched_filenames:
                        self.strategy = u'search_by_filepath[partial]'

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=False)
                if matched_filenames:
                    self.strategy = u'search_by_keywords!exact'

            if matched_filenames:
                matched_filenames += self.include_modules_from_test_targets(matched_filenames)

        return matched_filenames

    def search_by_botmeta_migrated_to(self, component):
        '''Is this a file belonging to a collection?'''

        matches = []

        # narrow searching to modules/utils/plugins
        if component.startswith('lib/ansible') and not (
                component.startswith('lib/ansible/plugins') or not
                component.startswith('lib/ansible/module')):
            return matches

        if os.path.basename(component) == '__init__.py':
            return matches

        if component.startswith('test/lib'):
            return matches

        # check for matches in botmeta first in case there's a migrated_to key ...
        botmeta_candidates = []
        for bmkey in self.botmeta[u'files'].keys():
            # skip tests because we dont want false positives
            if not bmkey.startswith('lib/ansible'):
                continue
            if not self.botmeta[u'files'][bmkey].get(u'migrated_to'):
                continue

            if u'modules/' in component and u'modules/' not in bmkey:
                continue
            if u'lookup' in component and u'lookup' not in bmkey:
                continue
            if u'filter' in component and u'filter' not in bmkey:
                continue
            if u'inventory' in component and u'inventory' not in bmkey:
                continue

            if bmkey == component or os.path.basename(bmkey).replace('.py', '') == os.path.basename(component).replace('.py', ''):
                mt = self.botmeta['files'][bmkey].get('migrated_to')[0]
                for fn,gcollections in self.GALAXY_FILES.items():
                    if mt not in gcollections:
                        continue
                    if os.path.basename(fn).replace('.py', '') != os.path.basename(component).replace('.py', ''):
                        continue
                    if u'modules/' in component and u'modules/' not in fn:
                        continue
                    if u'lookup' in component and u'lookup' not in fn:
                        continue
                    if u'filter' in component and u'filter' not in fn:
                        continue
                    if u'inventory' in component and u'inventory' not in fn:
                        continue
                    botmeta_candidates.append('collection:%s:%s' % (mt, fn))
                    logging.info('matched %s to %s to %s:%s' % (component, bmkey, mt, fn))

        if botmeta_candidates:
            return botmeta_candidates

        return matches

    """
    def search_by_galaxy(self, component):
        '''Is this a file belonging to a collection?'''

        matches = []

        # narrow searching to modules/utils/plugins
        if component.startswith('lib/ansible') and not (
                component.startswith('lib/ansible/plugins') or not
                component.startswith('lib/ansible/module')):
            return matches

        if os.path.basename(component) == '__init__.py':
            return matches

        if component.startswith('test/lib'):
            return matches

        candidates = []
        for key in self.GALAXY_FILES.keys():
            if not (component in key or key == component):
                continue
            if not key.startswith('plugins'):
                continue
            keybn = os.path.basename(key).replace('.py', '')
            if keybn != component:
                continue

            logging.info(u'matched %s to %s:%s' % (component, key, self.GALAXY_FILES[key]))
            candidates.append(key)

        if candidates:
            for cn in candidates:
                for fqcn in self.GALAXY_FILES[cn]:
                    if fqcn.startswith('testing.'):
                        continue
                    matches.append('collection:%s:%s' % (fqcn, cn))
            matches = sorted(set(matches))

        #import epdb; epdb.st()

        return matches
    """

    def search_by_module_name(self, component):
        matches = []

        component = self.clean_body(component)

        # docker-container vs. docker_container
        if component not in self.MODULE_NAMES:
            component = component.replace(u'-', u'_')

        if component in self.MODULE_NAMES:
            mmatch = self.find_module_match(component)
            if mmatch:
                if isinstance(mmatch, list):
                    for x in mmatch:
                        matches.append(x[u'repo_filename'])
                else:
                    matches.append(mmatch[u'repo_filename'])

        return matches

    def search_by_keywords(self, component, exact=True):
        """Simple keyword search"""

        component = component.lower()
        matches = []
        if component in self.STOPWORDS:
            matches = [None]
        elif component in self.KEYWORDS:
            matches = [self.KEYWORDS[component]]
        elif not exact:
            for k, v in self.KEYWORDS.items():
                if u' ' + k + u' ' in component or u' ' + k + u' ' in component.lower():
                    logging.debug(u'keyword match: {}'.format(k))
                    matches.append(v)
                elif u' ' + k + u':' in component or u' ' + k + u':' in component:
                    logging.debug(u'keyword match: {}'.format(k))
                    matches.append(v)
                elif component.endswith(u' ' + k) or component.lower().endswith(u' ' + k):
                    logging.debug(u'keyword match: {}'.format(k))
                    matches.append(v)

                elif (k in component or k in component.lower()) and k in self.BLACKLIST:
                    logging.debug(u'blacklist  match: {}'.format(k))
                    matches.append(None)

        return matches

    def search_by_regex_urls(self, body):
        # http://docs.ansible.com/ansible/latest/copy_module.html
        # http://docs.ansible.com/ansible/latest/dev_guide/developing_modules.html
        # http://docs.ansible.com/ansible/latest/postgresql_db_module.html
        # [helm module](https//docs.ansible.com/ansible/2.4/helm_module.html)
        # Windows module: win_robocopy\nhttp://docs.ansible.com/ansible/latest/win_robocopy_module.html
        # Examples:\n* archive (https://docs.ansible.com/ansible/archive_module.html)\n* s3_sync (https://docs.ansible.com/ansible/s3_sync_module.html)
        # https//github.com/ansible/ansible/blob/devel/lib/ansible/modules/windows/win_dsc.ps1L228

        matches = []

        urls = re.findall(
            u'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            body
        )
        if urls:
            for url in urls:
                url = url.rstrip(u')')
                if u'/blob' in url and url.endswith(u'.py'):
                    parts = url.split(u'/')
                    bindex = parts.index(u'blob')
                    fn = u'/'.join(parts[bindex+2:])
                    matches.append(fn)
                elif u'_module.html' in url:
                    parts = url.split(u'/')
                    fn = parts[-1].replace(u'_module.html', u'')
                    choices = [x for x in self.gitrepo.files if u'/' + fn in x or u'/_' + fn in x]
                    choices = [x for x in choices if u'lib/ansible/modules' in x]

                    if len(choices) > 1:
                        choices = [x for x in choices if u'/' + fn + u'.py' in x or u'/' + fn + u'.ps1' in x or u'/_' + fn + u'.py' in x]

                    if not choices:
                        pass
                    elif len(choices) == 1:
                        matches.append(choices[0])
                    else:
                        pass
                else:
                    pass

        return matches

    def search_by_regex_modules(self, body):
        # foo module
        # foo and bar modules
        # foo* modules
        # foo* module

        body = body.lower()
        logging.debug(u'attempt regex match on: {}'.format(body))

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            r'\:\n(\S+)\.py',
            r'(\S+)\.py',
            r'\-(\s+)(\S+)(\s+)module',
            r'\`ansible_module_(\S+)\.py\`',
            r'module(\s+)\-(\s+)(\S+)',
            r'module(\s+)(\S+)',
            r'\`(\S+)\`(\s+)module',
            r'(\S+)(\s+)module',
            r'the (\S+) command',
            r'(\S+) \(.*\)',
            r'(\S+)\-module',
            r'modules/(\S+)',
            r'module\:(\s+)\`(\S+)\`',
            r'module\: (\S+)',
            r'module (\S+)',
            r'module `(\S+)`',
            r'module: (\S+)',
            r'new (\S+) module',
            r'the (\S+) module',
            r'the \"(\S+)\" module',
            r':\n(\S+) module',
            r'(\S+) module',
            r'(\S+) core module',
            r'(\S+) extras module',
            r':\n\`(\S+)\` module',
            r'\`(\S+)\` module',
            r'`(\S+)` module',
            r'(\S+)\* modules',
            r'(\S+) and (\S+)',
            r'(\S+) or (\S+)',
            r'(\S+) \+ (\S+)',
            r'(\S+) \& (\S)',
            r'(\S+) and (\S+) modules',
            r'(\S+) or (\S+) module',
            r'(\S+)_module',
            r'action: (\S+)',
            r'action (\S+)',
            r'ansible_module_(\S+)\.py',
            r'ansible_module_(\S+)',
            r'ansible_modules_(\S+)\.py',
            r'ansible_modules_(\S+)',
            r'(\S+) task',
            r'(\s+)\((\S+)\)',
            r'(\S+)(\s+)(\S+)(\s+)modules',
            r'(\S+)(\s+)module\:(\s+)(\S+)',
            r'\-(\s+)(\S+)(\s+)module',
            r'\:(\s+)(\S+)(\s+)module',
            r'\-(\s+)ansible(\s+)(\S+)(\s+)(\S+)(\s+)module',
            r'.*(\s+)(\S+)(\s+)module.*'
        ]

        matches = []

        logging.debug(u'check patterns against: {}'.format(body))

        for pattern in patterns:
            mobj = re.match(pattern, body, re.M | re.I)

            if mobj:
                logging.debug(u'pattern {} matched on "{}"'.format(pattern, body))

                for x in range(0, mobj.lastindex+1):
                    try:
                        mname = mobj.group(x)
                        logging.debug(u'mname: {}'.format(mname))
                        if mname == body:
                            continue
                        mname = self.clean_body(mname)
                        if not mname.strip():
                            continue
                        mname = mname.strip().lower()
                        if u' ' in mname:
                            continue
                        if u'/' in mname:
                            continue

                        mname = mname.replace(u'.py', u'').replace(u'.ps1', u'')
                        logging.debug(u'--> {}'.format(mname))

                        # attempt to match a module
                        module_match = self.find_module_match(mname)

                        if not module_match:
                            pass
                        elif isinstance(module_match, list):
                            for m in module_match:
                                matches.append(m[u'repo_filename'])
                        elif isinstance(module_match, dict):
                            matches.append(module_match[u'repo_filename'])
                    except Exception as e:
                        logging.error(e)

                if matches:
                    break

        return matches

    def search_by_regex_module_globs(self, body):
        # All AWS modules
        # BigIP modules
        # NXOS modules
        # azurerm modules

        matches = []
        body = self.clean_body(body)
        logging.debug(u'try globs on: {}'.format(body))

        keymap = {
            u'all': None,
            u'ec2': u'lib/ansible/modules/cloud/amazon',
            u'ec2_*': u'lib/ansible/modules/cloud/amazon',
            u'aws': u'lib/ansible/modules/cloud/amazon',
            u'amazon': u'lib/ansible/modules/cloud/amazon',
            u'google': u'lib/ansible/modules/cloud/google',
            u'gce': u'lib/ansible/modules/cloud/google',
            u'gcp': u'lib/ansible/modules/cloud/google',
            u'bigip': u'lib/ansible/modules/network/f5',
            u'nxos': u'lib/ansible/modules/network/nxos',
            u'azure': u'lib/ansible/modules/cloud/azure',
            u'azurerm': u'lib/ansible/modules/cloud/azure',
            u'openstack': u'lib/ansible/modules/cloud/openstack',
            u'ios': u'lib/ansible/modules/network/ios',
        }

        regexes = [
            r'(\S+) ansible modules',
            r'all (\S+) based modules',
            r'all (\S+) modules',
            r'.* all (\S+) modules.*',
            r'(\S+) modules',
            r'(\S+\*) modules',
            r'all cisco (\S+\*) modules',
        ]

        mobj = None
        for x in regexes:
            mobj = re.match(x, body)
            if mobj:
                logging.debug(u'matched glob: {}'.format(x))
                break

        if not mobj:
            logging.debug(u'no glob matches')

        if mobj:
            keyword = mobj.group(1)
            if not keyword.strip():
                pass
            elif keyword in keymap:
                if keymap[keyword]:
                    matches.append(keymap[keyword])
            else:

                if u'*' in keyword:
                    keyword = keyword.replace(u'*', u'')

                # check for directories first
                fns = [x for x in self.MODULE_NAMESPACE_DIRECTORIES if keyword in x]

                # check for files second
                if not fns:
                    fns = [x for x in self.gitrepo.module_files
                           if u'lib/ansible/modules' in x
                           and keyword in x]

                if fns:
                    matches += fns

        if matches:
            matches = sorted(set(matches))

        return matches

    def search_by_regex_generic(self, body):
        # foo dynamic inventory script
        # foo filter

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            [r'(.*) action plugin', u'lib/ansible/plugins/action'],
            [r'(.*) inventory plugin', u'lib/ansible/plugins/inventory'],
            [r'(.*) dynamic inventory', u'contrib/inventory'],
            [r'(.*) dynamic inventory (script|file)', u'contrib/inventory'],
            [r'(.*) inventory script', u'contrib/inventory'],
            [r'(.*) filter', u'lib/ansible/plugins/filter'],
            [r'(.*) jinja filter', u'lib/ansible/plugins/filter'],
            [r'(.*) jinja2 filter', u'lib/ansible/plugins/filter'],
            [r'(.*) template filter', u'lib/ansible/plugins/filter'],
            [r'(.*) fact caching plugin', u'lib/ansible/plugins/cache'],
            [r'(.*) fact caching module', u'lib/ansible/plugins/cache'],
            [r'(.*) lookup plugin', u'lib/ansible/plugins/lookup'],
            [r'(.*) lookup', u'lib/ansible/plugins/lookup'],
            [r'(.*) callback plugin', u'lib/ansible/plugins/callback'],
            [r'(.*)\.py callback', u'lib/ansible/plugins/callback'],
            [r'callback plugin (.*)', u'lib/ansible/plugins/callback'],
            [r'(.*) stdout callback', u'lib/ansible/plugins/callback'],
            [r'stdout callback (.*)', u'lib/ansible/plugins/callback'],
            [r'stdout_callback (.*)', u'lib/ansible/plugins/callback'],
            [r'(.*) callback plugin', u'lib/ansible/plugins/callback'],
            [r'(.*) connection plugin', u'lib/ansible/plugins/connection'],
            [r'(.*) connection type', u'lib/ansible/plugins/connection'],
            [r'(.*) connection', u'lib/ansible/plugins/connection'],
            [r'(.*) transport', u'lib/ansible/plugins/connection'],
            [r'connection=(.*)', u'lib/ansible/plugins/connection'],
            [r'connection: (.*)', u'lib/ansible/plugins/connection'],
            [r'connection (.*)', u'lib/ansible/plugins/connection'],
            [r'strategy (.*)', u'lib/ansible/plugins/strategy'],
            [r'(.*) strategy plugin', u'lib/ansible/plugins/strategy'],
            [r'(.*) module util', u'lib/ansible/module_utils'],
            [r'ansible-galaxy (.*)', u'lib/ansible/galaxy'],
            [r'ansible-playbook (.*)', u'lib/ansible/playbook'],
            [r'ansible/module_utils/(.*)', u'lib/ansible/module_utils'],
            [r'module_utils/(.*)', u'lib/ansible/module_utils'],
            [r'lib/ansible/module_utils/(.*)', u'lib/ansible/module_utils'],
            [r'(\S+) documentation fragment', u'lib/ansible/utils/module_docs_fragments'],
        ]

        body = self.clean_body(body)

        matches = []

        for pattern in patterns:
            mobj = re.match(pattern[0], body, re.M | re.I)

            if mobj:
                logging.debug(u'pattern hit: {}'.format(pattern))
                fname = mobj.group(1)
                fname = fname.lower()

                fpath = os.path.join(pattern[1], fname)

                if fpath in self.gitrepo.files:
                    matches.append(fpath)
                elif os.path.join(pattern[1], fname + u'.py') in self.gitrepo.files:
                    fname = os.path.join(pattern[1], fname + u'.py')
                    matches.append(fname)
                else:
                    # fallback to the directory
                    matches.append(pattern[1])

        return matches

    def search_by_tracebacks(self, body):

        matches = []

        if u'Traceback (most recent call last)' in body:
            lines = body.split(u'\n')
            for line in lines:
                line = line.strip()
                if line.startswith(u'DistributionNotFound'):
                    matches = [u'setup.py']
                    break
                elif line.startswith(u'File'):
                    fn = line.split()[1]
                    for SC in self.STOPCHARS:
                        fn = fn.replace(SC, u'')
                    if u'ansible_module_' in fn:
                        fn = os.path.basename(fn)
                        fn = fn.replace(u'ansible_module_', u'')
                        matches = [fn]
                    elif u'cli/playbook.py' in fn:
                        fn = u'lib/ansible/cli/playbook.py'
                    elif u'module_utils' in fn:
                        idx = fn.find(u'module_utils/')
                        fn = u'lib/ansible/' + fn[idx:]
                    elif u'ansible/' in fn:
                        idx = fn.find(u'ansible/')
                        fn1 = fn[idx:]

                        if u'bin/' in fn1:
                            if not fn1.startswith(u'bin'):

                                idx = fn1.find(u'bin/')
                                fn1 = fn1[idx:]

                                if fn1.endswith(u'.py'):
                                    fn1 = fn1.rstrip(u'.py')

                        elif u'cli/' in fn1:
                            idx = fn1.find(u'cli/')
                            fn1 = fn1[idx:]
                            fn1 = u'lib/ansible/' + fn1

                        elif u'lib' not in fn1:
                            fn1 = u'lib/' + fn1

                        if fn1 not in self.files:
                            pass

        return matches

    def search_by_filepath(self, body, partial=False, context=None):
        """Find known filepaths in body"""

        matches = []
        body = self.clean_body(body)

        if not body:
            return []
        if body.lower() in self.STOPCHARS:
            return []
        if body.lower() in self.STOPWORDS:
            return []

        # 'inventory manager' vs. 'inventory/manager'
        if partial and u' ' in body:
            body = body.replace(u' ', u'/')

        if u'site-packages' in body:
            res = re.match(u'(.*)/site-packages/(.*)', body)
            if res:
                body = res.group(2)
        if u'modules/core/' in body:
            body = body.replace(u'modules/core/', u'modules/')
        if u'modules/extras/' in body:
            body = body.replace(u'modules/extras/', u'modules/')
        if u'ansible-modules-core/' in body:
            body = body.replace(u'ansible-modules-core/', u'/')
        if u'ansible-modules-extras/' in body:
            body = body.replace(u'ansible-modules-extras/', u'/')
        if body.startswith(u'ansible/lib/ansible'):
            body = body.replace(u'ansible/lib', u'lib')
        if body.startswith(u'ansible/') and not body.startswith(u'ansible/modules'):
            body = body.replace(u'ansible/', u'', 1)
        if u'module/' in body:
            body = body.replace(u'module/', u'modules/')

        logging.debug(u'search filepath [{}] [{}]: {}'.format(context, partial, body))

        if len(body) < 2:
            return []

        if u'/' in body:
            body_paths = body.split(u'/')
        elif u' ' in body:
            body_paths = body.split()
            body_paths = [x.strip() for x in body_paths if x.strip()]
        else:
            body_paths = [body]

        if u'networking' in body_paths:
            ix = body_paths.index(u'networking')
            body_paths[ix] = u'network'
        if u'plugin' in body_paths:
            ix = body_paths.index(u'plugin')
            body_paths[ix] = u'plugins'

        if not context or u'lib/ansible/modules' in context:
            mmatch = self.find_module_match(body)
            if mmatch:
                if isinstance(mmatch, list) and len(mmatch) > 1:
                    # another modules dir flattening mitigation
                    if len(mmatch) == 2:
                        if MODULES_FLATTEN_MAP.get(mmatch[1][u'repo_filename'], '') == mmatch[0][u'repo_filename']:
                            return [mmatch[0][u'repo_filename']]

                    # only allow for exact prefix globbing here ...
                    if [x for x in mmatch if x[u'repo_filename'].startswith(body)]:
                        return [x[u'repo_filename'] for x in mmatch]

                elif isinstance(mmatch, list):
                    return [x[u'repo_filename'] for x in mmatch]
                else:
                    return [mmatch[u'repo_filename']]

        if body in self.gitrepo.files:
            matches = [body]
        else:
            for fn in self.gitrepo.files:

                # limit the search set if a context is given
                if context is not None and not fn.startswith(context):
                    continue

                if fn.endswith((body, body + u'.py', body + u'.ps1')):
                    # ios_config.py -> test_ios_config.py vs. ios_config.py
                    bn1 = os.path.basename(body)
                    bn2 = os.path.basename(fn)
                    if bn2.startswith(bn1):
                        matches = [fn]
                        break

                if partial:

                    # netapp_e_storagepool storage module
                    # lib/ansible/modules/storage/netapp/netapp_e_storagepool.py

                    # if all subpaths are in this filepath, it is a match
                    bp_total = 0
                    fn_paths = fn.split(u'/')
                    fn_paths.append(fn_paths[-1].replace(u'.py', u'').replace(u'.ps1', u''))

                    for bp in body_paths:
                        if bp in fn_paths:
                            bp_total += 1

                    if bp_total == len(body_paths):
                        matches = [fn]
                        break

                    elif bp_total > 1:

                        if (float(bp_total) / float(len(body_paths))) >= (2.0 / 3.0):
                            if fn not in matches:
                                matches.append(fn)

        if matches:
            tr = []
            for match in matches[:]:
                # reduce to longest path
                for m in matches:
                    if match == m:
                        continue
                    if len(m) < len(match) and match.startswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    logging.debug(u'trimming {}'.format(r))
                    matches.remove(r)

        matches = sorted(set(matches))
        logging.debug(u'return: {}'.format(matches))

        return matches

    def reduce_filepaths(self, matches):

        # unique
        _matches = []
        for _match in matches:
            if _match not in _matches:
                _matches.append(_match)
        matches = _matches[:]

        # squash to longest path
        if matches:
            tr = []
            for match in matches[:]:
                # reduce to longest path
                for m in matches:
                    if match == m:
                        continue
                    if m is None or match is None:
                        continue
                    if len(m) < len(match) and match.startswith(m) or match.endswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    matches.remove(r)
        return matches

    def include_modules_from_test_targets(self, matches):
        """Map test targets to the module files"""
        new_matches = []
        for match in matches:
            if not match:
                continue
            # include modules from test targets
            if u'test/integration/targets' in match:
                paths = match.split(u'/')
                tindex = paths.index(u'targets')
                mname = paths[tindex+1]
                mrs = self.find_module_match(mname, exact=True)
                if mrs:
                    if not isinstance(mrs, list):
                        mrs = [mrs]
                    for mr in mrs:
                        new_matches.append(mr[u'repo_filename'])
        return new_matches

    def _filenames_to_keys(self, filenames):
        '''Match filenames to the keys in botmeta'''
        ckeys = set()
        for filen in filenames:
            if filen in self.botmeta[u'files']:
                ckeys.add(filen)
            for key in self.botmeta[u'files'].keys():
                if filen.startswith(key):
                    ckeys.add(key)
        return list(ckeys)

    def get_labels_for_files(self, files):
        labels = []
        for fn in files:
            for label in self.get_meta_for_file(fn).get(u'labels', []):
                if label not in [u'ansible', u'lib'] and label not in labels:
                    labels.append(label)
        return labels

    def get_meta_for_file(self, filename):
        meta = {
            u'collection': None,
            u'collection_scm': None,
            u'repo_filename': filename,
            u'name': os.path.basename(filename).split(u'.')[0],
            u'notify': [],
            u'assign': [],
            u'authors': [],
            u'committers': [],
            u'maintainers': [],
            u'labels': [],
            u'ignore': [],
            u'support': None,
            u'supported_by': None,
            u'deprecated': False,
            u'topic': None,
            u'subtopic': None,
            u'supershipit': [],
            u'namespace': None,
            u'namespace_maintainers': [],
            u'metadata': {},
            u'migrated_to': None,
            u'keywords': [],
        }

        if filename.startswith(u'collection:'):
            fqcn = filename.split(u':')[1]
            manifest = self.GALAXY_MANIFESTS.get(fqcn)
            if manifest:
                manifest = manifest[u'manifest'][u'collection_info']
            meta[u'collection'] = fqcn
            meta[u'migrated_to'] = fqcn
            meta[u'support'] = u'community'
            manifest = self.GALAXY_MANIFESTS.get(fqcn)
            if manifest:
                manifest = manifest[u'manifest'][u'collection_info']
                if manifest.get(u'repository'):
                    meta[u'collection_scm'] = manifest[u'repository']
                elif manifest.get(u'issues'):
                    meta[u'collection_scm'] = manifest[u'issues']
            return meta

        populated = False
        filenames = [filename, os.path.splitext(filename)[0]]

        # powershell meta is in the python file
        if filename.endswith(u'.ps1'):
            pyfile = filename.replace(u'.ps1', u'.py')
            if pyfile in self.botmeta[u'files']:
                filenames.append(pyfile)

        botmeta_entries = self._filenames_to_keys(filenames)
        for bme in botmeta_entries:
            logging.debug(u'matched botmeta entry: %s' % bme)

        # Modules contain metadata in docstrings and that should
        # be factored in ...
        #   https://github.com/ansible/ansibullbot/issues/1042
        #   https://github.com/ansible/ansibullbot/issues/1053
        if u'lib/ansible/modules' in filename:
            mmatch = self.find_module_match(filename)
            if mmatch and len(mmatch) == 1 and mmatch[0][u'filename'] == filename:
                meta[u'metadata'].update(mmatch[0][u'metadata'])
                for k in u'authors', u'maintainers':
                    meta[k] += mmatch[0][k]
                meta[u'notify'] += mmatch[0][u'notified']

            if meta[u'metadata']:
                if meta[u'metadata'][u'supported_by']:
                    meta[u'support'] = meta[u'metadata'][u'supported_by']

        # reconcile the delta between a child and it's parents
        support_levels = {}

        for entry in botmeta_entries:
            fdata = self.botmeta[u'files'][entry].copy()

            if u'authors' in fdata:
                meta[u'notify'] += fdata[u'authors']
                meta[u'authors'] += fdata[u'authors']
            if u'maintainers' in fdata:
                meta[u'notify'] += fdata[u'maintainers']
                meta[u'assign'] += fdata[u'maintainers']
                meta[u'maintainers'] += fdata[u'maintainers']
            if u'notified' in fdata:
                meta[u'notify'] += fdata[u'notified']
            if u'labels' in fdata:
                meta[u'labels'] += fdata[u'labels']
            if u'ignore' in fdata:
                meta[u'ignore'] += fdata[u'ignore']
            if u'ignored' in fdata:
                meta[u'ignore'] += fdata[u'ignored']
            if u'migrated_to' in fdata and meta[u'migrated_to'] is None:
                meta[u'migrated_to'] = fdata[u'migrated_to']
            if u'keywords' in fdata:
                meta[u'keywords'] += fdata[u'keywords']

            if u'support' in fdata:
                if isinstance(fdata[u'support'], list):
                    support_levels[entry] = fdata[u'support'][0]
                else:
                    support_levels[entry] = fdata[u'support']
            elif u'supported_by' in fdata:
                if isinstance(fdata[u'supported_by'], list):
                    support_levels[entry] = fdata[u'supported_by'][0]
                else:
                    support_levels[entry] = fdata[u'supported_by']

            # only "deprecate" exact matches
            if u'deprecated' in fdata and entry == filename:
                meta[u'deprecated'] = fdata[u'deprecated']

            populated = True

        # walk up the tree for more meta
        paths = filename.split(u'/')
        for idx, x in enumerate(paths):
            thispath = u'/'.join(paths[:(0-idx)])
            if thispath in self.botmeta[u'files']:
                fdata = self.botmeta[u'files'][thispath].copy()
                if u'support' in fdata:
                    if isinstance(fdata[u'support'], list):
                        support_levels[thispath] = fdata[u'support'][0]
                    else:
                        support_levels[thispath] = fdata[u'support']
                elif u'supported_by' in fdata:
                    if isinstance(fdata[u'supported_by'], list):
                        support_levels[thispath] = fdata[u'supported_by'][0]
                    else:
                        support_levels[thispath] = fdata[u'supported_by']
                if u'labels' in fdata:
                    meta[u'labels'] += fdata[u'labels']
                if u'maintainers' in fdata:
                    meta[u'notify'] += fdata[u'maintainers']
                    meta[u'assign'] += fdata[u'maintainers']
                    meta[u'maintainers'] += fdata[u'maintainers']
                if u'ignore' in fdata:
                    meta[u'ignore'] += fdata[u'ignore']
                if u'notified' in fdata:
                    meta[u'notify'] += fdata[u'notified']

        if u'lib/ansible/modules' in filename:
            topics = [x for x in paths if x not in [u'lib', u'ansible', u'modules']]
            topics = [x for x in topics if x != os.path.basename(filename)]
            if len(topics) == 2:
                meta[u'topic'] = topics[0]
                meta[u'subtopic'] = topics[1]
            elif len(topics) == 1:
                meta[u'topic'] = topics[0]

            meta[u'namespace'] = u'/'.join(topics)

        # set namespace maintainers (skip !modules for now)
        if filename.startswith(u'lib/ansible/modules'):
            ns = meta.get(u'namespace')
            keys = self.botmeta[u'files'].keys()
            keys = [x for x in keys if x.startswith(os.path.join(u'lib/ansible/modules', ns))]
            ignored = []

            for key in keys:
                meta[u'namespace_maintainers'] += self.botmeta[u'files'][key].get(u'maintainers', [])
                ignored += self.botmeta[u'files'][key].get(u'ignored', [])

            for ignoree in ignored:
                while ignoree in meta[u'namespace_maintainers']:
                    meta[u'namespace_maintainers'].remove(ignoree)

        # reconcile support levels
        if filename in support_levels:
            # exact match
            meta[u'support'] = support_levels[filename]
            meta[u'supported_by'] = support_levels[filename]
            logging.debug(u'%s support == %s' % (filename, meta[u'supported_by']))
        else:
            # pick the closest match
            keys = support_levels.keys()
            keys = sorted(keys, key=len, reverse=True)
            if keys:
                meta[u'support'] = support_levels[keys[0]]
                meta[u'supported_by'] = support_levels[keys[0]]
                logging.debug(u'%s support == %s' % (keys[0], meta[u'supported_by']))

        '''
        # new modules should default to "community" support
        if filename.startswith(u'lib/ansible/modules') and filename not in self.gitrepo.files and not meta.get('migrated_to'):
            meta[u'support'] = u'community'
            meta[u'supported_by'] = u'community'
        '''

        # test targets for modules should inherit from their modules
        if filename.startswith(u'test/integration/targets') and filename not in self.botmeta[u'files']:
            whitelist = [
                u'labels',
                u'ignore',
                u'deprecated',
                u'authors',
                u'assign',
                u'maintainers',
                u'notify',
                u'topic',
                u'subtopic',
                u'support'
            ]

            paths = filename.split(u'/')
            tindex = paths.index(u'targets')
            mname = paths[tindex+1]
            mmatch = self._find_module_match(mname, exact=True)
            if mmatch:
                mmeta = self.get_meta_for_file(mmatch[0][u'repo_filename'])
                for k, v in mmeta.items():
                    if k in whitelist and v:
                        if isinstance(meta[k], list):
                            meta[k] = sorted(set(meta[k] + v))
                        elif not meta[k]:
                            meta[k] = v

            # make new test targets community by default
            if not meta[u'support'] and not meta[u'supported_by']:
                #import epdb; epdb.st()
                meta[u'support'] = u'community'

        # it's okay to remove things from legacy-files.txt
        if filename == u'test/sanity/pep8/legacy-files.txt' and not meta[u'support']:
            meta[u'support'] = u'community'

        # get support from the module metadata ...
        if meta.get(u'metadata'):
            if meta[u'metadata'].get(u'supported_by'):
                meta[u'support'] = meta[u'metadata'][u'supported_by']
                meta[u'supported_by'] = meta[u'metadata'][u'supported_by']

        # fallback to core support
        if not meta[u'support']:
            meta[u'support'] = u'core'

        # align support and supported_by
        if meta[u'support'] != meta[u'supported_by']:
            if meta[u'support'] and not meta[u'supported_by']:
                meta[u'supported_by'] = meta[u'support']
            elif not meta[u'support'] and meta[u'supported_by']:
                meta[u'support'] = meta[u'supported_by']

        # clean up the result
        _meta = meta.copy()
        for k, v in _meta.items():
            if isinstance(v, list):
                meta[k] = sorted(set(v))

        def get_prefix_paths(repo_filename, files):
            """Emit all prefix paths matching the given file list."""
            if not repo_filename:
                return

            prefix_paths = make_prefixes(repo_filename)

            for prefix_path in prefix_paths:
                if prefix_path in files:
                    logging.debug(u'found botmeta prefix: {}'.format(prefix_path))
                    yield prefix_path

        # walk up the botmeta tree looking for meta to include
        for this_prefix in get_prefix_paths(
            meta.get(u'repo_filename'), self.botmeta[u'files'],
        ):

            this_ignore = (
                self.botmeta[u'files'][this_prefix].get(u'ignore') or
                self.botmeta[u'files'][this_prefix].get(u'ignored') or
                self.botmeta[u'files'][this_prefix].get(u'ignores') or
                []
            )

            for username in this_ignore:
                if username not in meta[u'ignore']:
                    logging.info(u'ignored: {}'.format(this_ignore))
                    meta[u'ignore'].append(username)
                if username in meta[u'notify']:
                    logging.info('remove %s notify by %s rule' % \
                        (username, this_prefix))
                    meta[u'notify'].remove(username)
                if username in meta[u'assign']:
                    logging.info('remove %s assignment by %s rule' % \
                        (username, this_prefix))
                    meta[u'assign'].remove(username)
                if username in meta[u'maintainers']:
                    logging.info('remove %s maintainer by %s rule' % \
                        (username, this_prefix))
                    meta[u'maintainers'].remove(username)

            this_supershipit = self.botmeta[u'files'][this_prefix].get(
                u'supershipit', [],
            )

            for username in this_supershipit:
                if username not in meta[u'supershipit']:
                    logging.info(u'supershipiteer: {}'.format(this_prefix))
                    meta[u'supershipit'].append(username)

        return meta

    def find_module_match(self, pattern, exact=False):
        '''Exact module name matching'''

        logging.debug(u'find_module_match for "{}"'.format(pattern))
        candidate = None

        BLACKLIST = [
            u'module_utils',
            u'callback',
            u'network modules',
            u'networking modules'
            u'windows modules'
        ]

        if not pattern or pattern is None:
            return None

        # https://github.com/ansible/ansible/issues/19755
        if pattern == u'setup':
            pattern = u'lib/ansible/modules/system/setup.py'

        if u'/facts.py' in pattern or u' facts.py' in pattern:
            pattern = u'lib/ansible/modules/system/setup.py'

        # https://github.com/ansible/ansible/issues/18527
        #   docker-container -> docker_container
        if u'-' in pattern:
            pattern = pattern.replace(u'-', u'_')

        if u'module_utils' in pattern:
            # https://github.com/ansible/ansible/issues/20368
            return None
        elif u'callback' in pattern:
            return None
        elif u'lookup' in pattern:
            return None
        elif u'contrib' in pattern and u'inventory' in pattern:
            return None
        elif pattern.lower() in BLACKLIST:
            return None

        candidate = self._find_module_match(pattern, exact=exact)

        if not candidate:
            candidate = self._find_module_match(os.path.basename(pattern))

        if not candidate and u'/' in pattern and not pattern.startswith(u'lib/'):
            ppy = None
            ps1 = None
            if not pattern.endswith(u'.py') and not pattern.endswith(u'.ps1'):
                ppy = pattern + u'.py'
            if not pattern.endswith(u'.py') and not pattern.endswith(u'.ps1'):
                ps1 = pattern + u'.ps1'
            for mf in self.gitrepo.module_files:
                if pattern in mf:
                    if mf.endswith((pattern, ppy, ps1)):
                        candidate = mf
                        break

        return candidate

    def _find_module_match(self, pattern, exact=False):

        logging.debug(u'matching on {}'.format(pattern))

        matches = []

        if isinstance(pattern, six.text_type):
            pattern = to_text(to_bytes(pattern, 'ascii', 'ignore'), 'ascii')

        logging.debug(u'_find_module_match: {}'.format(pattern))

        noext = pattern.replace(u'.py', u'').replace(u'.ps1', u'')

        # exact is looking for a very precise name such as "vmware_guest"
        if exact:
            candidates = [pattern]
        else:
            candidates = [pattern, u'_' + pattern, noext, u'_' + noext]

        for k, v in self.MODULES.items():
            if v[u'name'] in candidates:
                logging.debug(u'match {} on name: {}'.format(k, v[u'name']))
                matches = [v]
                break

        if not matches:
            # search by key ... aka the filepath
            for k, v in self.MODULES.items():
                if k == pattern:
                    logging.debug(u'match {} on key: {}'.format(k, k))
                    matches = [v]
                    break

        # spellcheck
        if not exact and not matches and u'/' not in pattern:
            _pattern = pattern
            if not isinstance(_pattern, six.text_type):
                _pattern = to_text(_pattern)
            candidates = []
            for k, v in self.MODULES.items():
                vname = v[u'name']
                if not isinstance(vname, six.text_type):
                    vname = to_text(vname)
                jw = jaro_winkler(vname, _pattern)
                if jw > .9:
                    candidates.append((jw, k))
            for candidate in candidates:
                matches.append(self.MODULES[candidate[1]])

        return matches
