#!/usr/bin/python
# -*- coding: <utf-8> -*-
import ConfigParser
import subprocess
import sys
import os
import tempfile
from distutils import dir_util, file_util
from distutils.spawn import find_executable
import requests
from setuptools import Command
try:
    from docker import Client
except:
    pass

try:
    from pkginfo import UnpackedSDist
except:
    pass


class BdistAmp(Command):

    description = "bdist_amp command for amp (must use with sudo)"

    user_options = []

    def initialize_options(self):

        pass

    def finalize_options(self):

        pass

    def run(self):

        c = Client()
        cur_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        dir_name = cur_dir.rsplit("/", 1)[1]
        if not os.path.exists(os.path.join(cur_dir, "ampdist.conf")):
            print cur_dir + "ampdist.conf not found."

        else:
            config = ConfigParser.RawConfigParser()
            config.read(os.path.join(cur_dir, 'ampdist.conf'))
            base_name = config.get('Image', 'base_name')
            base_ver = config.get('Image', 'base_ver')
            base_fname = base_name + ":" + base_ver
            if find_executable("docker") is None:
                print "docker command is not found"
                print "installing docker.io..."
                subprocess.call(["wget", "-qO-", "https://get.docker.com/", "|", "sh"])

            im_list = c.images(name=base_fname, quiet=True)

            if im_list:
                im_id = im_list[0].split(':')[1].encode('ascii')

            else:
                print base_fname + " is not found."
                c.pull(base_name, tag=base_ver)

            hvol_path = tempfile.mkdtemp()
            cvol_path = "/export/"
            cont_id = c.create_container(base_fname, command="/bin/bash", volumes=[cvol_path],
                               host_config=c.create_host_config(binds={
                                   hvol_path: cvol_path
                               }),
                               detach=True, stdin_open=True, tty=True)['Id']
            c.start(cont_id)
            dir_util.copy_tree(cur_dir, os.path.join(hvol_path,dir_name))
            command_1 = "cd " + cvol_path + dir_name + " && python " + sys.argv[0] + " install"
            exec_comm_1 = """bash -c "%s" """ % command_1
            exec_1 = c.exec_create(cont_id, exec_comm_1)
            for line in c.exec_start(exec_1, stream=True):
                print line

            cur_pack = UnpackedSDist(cur_dir)
            pack_name = (cur_pack.name + '-' + cur_pack.version).encode('ascii')
            diffs = c.diff(cont_id)
            diff_file = open(hvol_path + '/diff_text_not_true.txt', 'w')
            for i in diffs:
                if i['Kind'] == 1:
                    diff_file.writelines(i['Path'] + '\n')

            diff_file.close()
            command_2 = "cd " + cvol_path + dir_name + " && python " + sys.argv[0] + " gendiff"
            exec_comm_2 = """bash -c "%s" """ % command_2
            exec_2 = c.exec_create(cont_id, exec_comm_2)
            for line in c.exec_start(exec_2, stream=True):
                print line

            exec_comm_3 = "tar", "-cvf", \
                        cvol_path + pack_name + ".tar.gz", "-T", \
                        cvol_path + "/diff_text.txt"
            exec_3 = c.exec_create(cont_id,exec_comm_3)
            for line in c.exec_start(exec_3, stream=True):
                print line

            c.stop(cont_id, timeout=1)
            c.remove_container(cont_id)
            if not os.path.exists(os.path.join(cur_dir, "bdist")):
                os.makedirs(os.path.join(cur_dir, "bdist"))

            file_util.copy_file(os.path.join(hvol_path, pack_name) + ".tar.gz",
                                os.path.join(cur_dir, "bdist"))
            dir_util.remove_tree(hvol_path)


class UploadBdist(Command):

    description = "upload_amp command for amp"

    user_options = []

    def initialize_options(self):

        pass

    def finalize_options(self):

        pass

    def run(self):

        cur_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        cur_pack = UnpackedSDist(cur_dir)
        pack_name = cur_pack.name.encode('ascii','ignore')
        version = cur_pack.version.encode('ascii','ignore')
        full_name = (pack_name + "-" + version).encode('ascii','ignore')
        if not os.path.exists(os.path.join(cur_dir, "bdist") + "/" + full_name + ".tar.gz"):
            print os.path.join(cur_dir, "bdist") + "/" + full_name + ".tar.gz not found."

        else:
            if not os.path.exists(os.path.join(cur_dir, "ampdist.conf")):
                print cur_dir + "ampdist.conf not found."

            else:
                config = ConfigParser.RawConfigParser()
                config.read(os.path.join(cur_dir, 'ampdist.conf'))
                user_name = config.get('Auth', 'user_name')
                password = config.get('Auth', 'password')
                url = config.get('Url', 'server_url')
                base_ver = config.get('Image', 'base_ver')
                base_name = config.get('Image', 'base_name')
                r = requests.Session()
                f = {'data': open(os.path.join(cur_dir, "bdist") + "/" + full_name + ".tar.gz", 'rb')}
                resp = r.post(url+"/authn_http",
                              params={'user_name': user_name, 'password': password})
                if resp.status_code == requests.codes.ok:
                    try:
                        jresp = r.get(url+"/api-json/get_wagon",
                                      params={"wagon.name": pack_name}).json()
                        wagon_id = jresp['id']
                    except:
                        resp = r.post(url + "/put_wagon", params={"name": pack_name})
                        jresp = r.get(url + "/api-json/get_wagon",
                                      params={"wagon.name": pack_name}).json()
                        wagon_id = jresp['id']

                    package_is_exist = False
                    for rempacks in jresp['rempacks']:
                        if rempacks['version'] == version \
                                and rempacks['base_ver'] == base_ver \
                                and rempacks['base_name'] == base_name:
                            print "This version of package is exist for this base."
                            package_is_exist = True
                            break

                    if package_is_exist is False:
                        r.post(url+"/put_rempack",
                               params={"version": version,
                                       "wagon.id": wagon_id,
                                       "base_ver": base_ver,
                                       "base_name": base_name
                                       },
                               files=f)


class GenDiffFile(Command):

    description = "not for users"

    user_options = []

    def initialize_options(self):

        pass

    def finalize_options(self):

        pass

    def run(self):


        cvol_path = "/export/"
        diff_file_not_true = open(os.path.join(cvol_path, "diff_text_not_true.txt"), 'r')
        diff_file = open(os.path.join(cvol_path, "diff_text.txt"), 'w')
        for i in diff_file_not_true.readlines():
            i = i.split()[0]
            if not os.path.isdir(i):
                diff_file.writelines(i + "\n")

        diff_file_not_true.close()
        diff_file.close()



# for use in your projects
# add following lines to setup.py:
# from ampdist.py import BdistAmp
# setup(
#              ...
#            cmdclass={'bdist_amp': BdistAmp,
#                       'upload_amp': UploadBdist,
#                       'gendiff': GenDiffFile,
#                       },
#               ...
#        )
# usage: python setup.py bdist_amp

