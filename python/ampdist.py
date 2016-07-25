#!/usr/bin/python
# -*- coding: <utf-8> -*-

import subprocess
import sys
import os
import tempfile
import shutil
from setuptools import find_packages
from setuptools import Command


class BdistAmp(Command):

    description = "bdist command for amp (must use with sudo)"

    user_options = []

    def initialize_options(self):

        pass

    def finalize_options(self):

        pass

    def run(self):

        arsbas = "arskom/base"
        try:
            im_id = subprocess.check_output(["docker", "images", "-q", arsbas])
            im_id = im_id.split()[0]
        except OSError as e:
            print "docker command is not found"
            print "installing docker.io..."
            subprocess.call(["wget", "-qO-", "https://get.docker.com/", "|", "sh"])
            im_id = subprocess.check_output(["docker", "images", "-q", arsbas])
            im_id = im_id.split()[0]

        if not im_id.isalnum():
            print arsbas + " is not found."
            subprocess.call(["docker", "pull", arsbas])

        hvol_path = tempfile.mkdtemp()                                  # Host shared data volume.
        cvol_path = "/export/"                                          # Container shared data volume.
        subprocess.call(["docker", "run", "-v", hvol_path + ":" + cvol_path,
                         "-itd", arsbas, "/bin/bash"])
        cont_id = subprocess.check_output(["docker", "ps", "-alq"])
        cont_id = cont_id.split()[0]
        cur_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        dir_name = cur_dir.rsplit("/", 1)[1]
        subprocess.call(["docker", "cp", cur_dir, cont_id + ":" + cvol_path])
        subprocess.call(["docker", "exec", cont_id, "bash", "-c", "cd " + cvol_path + dir_name +
                        " && python " + sys.argv[0] + " install"])
        pack_name = find_packages()[0]
        diffs = subprocess.check_output(['docker', 'diff', cont_id])
        diff_list = diffs.split('\n')
        diff_file = open(hvol_path + '/diff_text.txt', 'w')
        for line in diff_list:
            if line.split(' ')[0] == 'A':
                diff_file.writelines(line.split(' ')[1] + '\n')

        diff_file.close()
        subprocess.call(["docker", "exec", cont_id,
                         "tar", "-cvPf", cvol_path + pack_name + ".tar.gz",
                         "-T", cvol_path + "/diff_text.txt"])
        subprocess.call(["docker", "stop", cont_id])
        subprocess.call(["docker", "rm", cont_id])
        if not os.path.exists(os.path.join(cur_dir, "bdist")):
            os.makedirs(os.path.join(cur_dir, "bdist"))

        shutil.copy(os.path.join(hvol_path, pack_name) + ".tar.gz", os.path.join(cur_dir, "bdist"))
        shutil.rmtree(hvol_path)

# for use in your projects
# add following lines to setup.py:
# from ampdist.py import BdistAmp
# setup(
#              ...
#            cmdclass={'bdist_amp': BdistAmp},
#               ...
#        )
# usage: python setup.py bdist_amp
