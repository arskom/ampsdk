#!/usr/bin/env python
# encoding: utf-8
#
# This file is part of the Arskom Mobile Platform SDK repository.
# Copyright (c) Arskom Ltd. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from __future__ import print_function

import os
import sys
import tempfile
import requests
import subprocess
import ConfigParser

from setuptools import Command

from distutils import dir_util, file_util
from distutils.spawn import find_executable

gen_diff_py = """
#!/usr/bin/env python
# encoding: utf-8
import os

cvol_path = "/export/"
diff_file_not_true = open(os.path.join(cvol_path, "diff_text_not_true.txt"), 'r')
diff_file = open(os.path.join(cvol_path, "diff_text.txt"), 'w')
for i in diff_file_not_true.readlines():
    i = i.split()[0]
    if not os.path.isdir(i):
        diff_file.writelines(i + "\\n")

diff_file_not_true.close()
diff_file.close()
"""


class AmpDistClient(object):
    def __init__(self, hvol_path=tempfile.mkdtemp(),
                 cvol_path="/export/",
                 base_full_name=None,
                 base_name=None,
                 base_ver=None,
                 cont_id=None):

        import docker

        self.client = docker.Client()

        self.hvol_path = hvol_path
        self.cvol_path = cvol_path
        self.base_full_name = base_full_name
        self.base_name = base_name
        self.base_ver = base_ver
        self.cont_id = cont_id
        self.debug_mode = False

    def exec_starter(self, command, stream=False):
        _exec = self.client.exec_create(self.cont_id, command)
        if stream is True:
            for i in self.client.exec_start(_exec, stream=True):
                print
                i

        else:
            self.client.exec_start(_exec)

    def gen_base_full_name(self, conf_path=None):
        if conf_path is None and (
                self.base_name is None or self.base_ver is None):
            print
            "must give conf_path or base_name and base_ver."
            return None

        elif conf_path is not None:
            config = ConfigParser.RawConfigParser()
            config.read(conf_path)
            self.base_name = config.get('Image', 'base_name')
            self.base_ver = config.get('Image', 'base_ver')
            self.base_full_name = self.base_name + ":" + self.base_ver
            return self.base_full_name

        else:
            self.base_full_name = self.base_name + ":" + self.base_ver
            return self.base_full_name

    def gen_diff_file(self):
        with open(os.path.join(self.hvol_path, "gen_diff.py"), 'w') \
                as gen_diff_file:
            gen_diff_file.writelines(gen_diff_py)

    def exec_gen_diff_file(self, stream=False):
        self.gen_diff_file_not_true()
        self.gen_diff_file()
        command = "cd " + self.cvol_path + " && python gen_diff.py"
        exec_comm = """bash -c "%s" """ % command
        self.exec_starter(exec_comm, stream=stream)

    def gen_diff_file_not_true(self):
        diffs = self.client.diff(self.cont_id)
        with open(self.hvol_path + '/diff_text_not_true.txt', 'w') \
                as diff_file:
            for i in diffs:
                if i['Kind'] == 1:
                    diff_file.writelines(i['Path'] + '\n')

    def diff_packager(self, pack_name, stream=False):
        exec_comm = "tar", "-cvf", \
                    os.path.join(self.cvol_path, pack_name), "-T", \
                    os.path.join(self.cvol_path, "diff_text.txt")
        self.exec_starter(exec_comm, stream=stream)

    def cont_destroyer(self, timeout=1):
        self.client.stop(self.cont_id, timeout=timeout)
        self.client.remove_container(self.cont_id)

    def image_search_and_download(self, download=True):
        im_list = self.client.images(name=self.base_full_name, quiet=True)
        if not im_list:
            if download is True:
                for response in self.client.pull(self.base_name,
                                                 tag=self.base_ver):
                    if response.has_key('error'):
                        return False
                return True
            return False
        return True

    def rm_hvol_path(self):
        if self.debug_mode is False:
            dir_util.remove_tree(self.hvol_path)

    def container_starter(self, start=True):
        ret = self.client.create_container(
            self.base_full_name, command="/bin/bash",
            volumes=[self.cvol_path],
            host_config=self.client.create_host_config(
                binds={
                    self.hvol_path: self.cvol_path
                }),
            detach=True, stdin_open=True, tty=True
        )
        self.cont_id = ret['Id']

        if start is True:
            self.client.start(self.cont_id)

        return self.cont_id


class BdistAmp(Command):
    description = "bdist_amp command for amp (must use with sudo)"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        amp_dist = AmpDistClient()

        cur_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        dir_name = cur_dir.rsplit("/", 1)[1]

        if not os.path.exists(os.path.join(cur_dir, "ampdist.conf")):
            print(cur_dir + "ampdist.conf not found.")

        else:
            amp_dist.gen_base_full_name(
                conf_path=os.path.join(cur_dir, 'ampdist.conf'))

            if find_executable("docker") is None:
                print
                "docker command is not found"
                print
                "installing docker.io..."
                subprocess.call(
                    ["wget", "-qO-", "https://get.docker.com/", "|", "sh"])

            if not amp_dist.image_search_and_download():
                amp_dist.rm_hvol_path()
                raise

            amp_dist.container_starter()

            dir_util.copy_tree(cur_dir,
                os.path.join(amp_dist.hvol_path, dir_name))

            command_1 = "cd " + amp_dist.cvol_path + dir_name + " && python " + \
                        sys.argv[0] + " install"
            exec_comm_1 = """bash -c "%s" """ % command_1
            amp_dist.exec_starter(exec_comm_1, stream=True)

            from pkginfo import UnpackedSDist
            cur_pack = UnpackedSDist(cur_dir)

            pack_name = (cur_pack.name + '-' + cur_pack.version).encode(
                'ascii') + ".tar.gz"

            amp_dist.exec_gen_diff_file(stream=True)
            amp_dist.diff_packager(pack_name, stream=True)
            amp_dist.cont_destroyer()

            if not os.path.exists(os.path.join(cur_dir, "bdist")):
                os.makedirs(os.path.join(cur_dir, "bdist"))

            file_util.copy_file(os.path.join(amp_dist.hvol_path, pack_name),
                os.path.join(cur_dir, "bdist"))

        amp_dist.rm_hvol_path()


class UploadBdist(Command):
    description = "upload_amp command for amp"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from pkginfo import UnpackedSDist

        cur_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        cur_pack = UnpackedSDist(cur_dir)

        pack_name = cur_pack.name.encode('ascii', 'ignore')
        version = cur_pack.version.encode('ascii', 'ignore')
        full_name = (pack_name + "-" + version).encode('ascii', 'ignore')

        file_name = os.path.join(cur_dir, "bdist") + "/" + full_name + ".tar.gz"
        if not os.path.exists(file_name):
            print(file_name, "not found.")
            return

        if not os.path.exists(os.path.join(cur_dir, "ampdist.conf")):
            print(cur_dir, "ampdist.conf not found.")
            return

        config = ConfigParser.RawConfigParser()
        config.read(os.path.join(cur_dir, 'ampdist.conf'))
        user_name = config.get('Auth', 'user_name')
        password = config.get('Auth', 'password')
        url = config.get('Url', 'server_url')
        base_ver = config.get('Image', 'base_ver')
        base_name = config.get('Image', 'base_name')

        r = requests.Session()
        f = {'data': open(file_name, 'rb')}
        resp = r.post(url + "/authn_http",
            params={'user_name': user_name, 'password': password})

        if resp.status_code != requests.codes.ok:
            print(resp.status_code, resp.text)
            return

        try:
            jresp = r.get(url + "/api-json/get_wagon",
                params={"wagon.name": pack_name}).json()
            wagon_id = jresp['id']

        except:
            resp = r.post(url + "/put_wagon", params={"name": pack_name})
            # TODO: Validate resp

            jresp = r.get(url + "/api-json/get_wagon",
                params={"wagon.name": pack_name}).json()

            wagon_id = jresp['id']

        for rempacks in jresp['rempacks']:
            if rempacks['version'] == version \
                    and rempacks['base_ver'] == base_ver \
                    and rempacks['base_name'] == base_name:
                print("This version of package is exist for this base.")
                break
        else:
            params = {
                "version": version,
                "wagon.id": wagon_id,
                "base_ver": base_ver,
                "base_name": base_name,
            }
            r.post(url + "/put_rempack", params=params, files=f)

# for use in your projects
# add following lines to setup.py:
# from ampdist.py import BdistAmp
# setup(
#              ...
#            cmdclass={'bdist_amp': BdistAmp,
#                       'upload_amp': UploadBdist,
#                       },
#               ...
#        )
# usage: python setup.py bdist_amp
