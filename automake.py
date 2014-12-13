#!/usr/bin/python

import os
import sys
import platform
import json

from os.path import exists


def tostr(items):
    str = ''
    for i in items:
        str += i
        str += ' '
    return str[:-1]


def rmfile(path):
    try:
        os.remove(path)
    except Exception:
        pass


class AutoMake:
    # link type
    lo_static_library = 'static'
    lo_program = 'program'
    lo_shared_library = 'shared'
    lo_none = 'none'

    def __init__(self, source_dir='./'):
        if not source_dir.endswith('/'):
            source_dir += '/'
        self.source_dir = source_dir
        self.object_dir = '../obj/'
        self.output_dir = '../out/'
        self.output_name = ''
        self.compiler = ''
        self.compile_options = ''
        self.link_options = ''
        self.link_type = AutoMake.lo_program
        self.includes = '-I./'
        self.header_filter = ['h', 'hh', 'hpp', None]
        self.source_filter = ['cc', 'c', 'cxx', 'cpp']
        self.set_default_compiler()

    def save(self, fpath=None):
        """ Save configurations to the file specified by fpath. """
        if fpath is None:
            return json.dumps(self.__dict__, indent=True)
        else:
            json.dump(self.__dict__, open(fpath, 'w'), indent=True)

    def load(self, fpath):
        """ Load configurations from an automake file. """
        d = json.load(open(fpath))
        self.source_dir = d['source_dir'].strip(' \t')
        self.object_dir = d['object_dir'].strip(' \t')
        self.output_dir = d['output_dir'].strip(' \t')
        self.output_name = d['output_name'].strip(' \t')
        self.compiler = d['compiler'].strip(' \t')
        self.compile_options = d['compile_options']
        self.link_options = d['link_options']
        self.link_type = d['link_type']
        self.includes = d['includes']
        self.header_filter = d['header_filter']
        self.source_filter = d['source_filter']
        return automake

    def set_default_compiler(self):
        """ Set compiler by current OS name.
          For Windows, default compiler is VC++ compiler 'cl.exe'
          For MacOS, default compiler is 'clang++'
          For other OS's, default compiler is 'g++'
        """
        osname = platform.system()
        if osname == 'Windows':
            self.compiler = 'cl.exe'
        elif osname == 'Darwin':
            self.compiler = 'clang++'
        else:
            self.compiler = 'g++'

    def get_output(self):
        if len(self.output_name) != 0:
            return self.output_name
        # if the output name is not specified, then use the directory name as output name
        dirname = os.path.realpath(self.source_dir)
        if dirname.endswith('/'):
            dirname = dirname[:-1]
        name = ''
        p = dirname.rfind('/')
        if p == -1:
            name = 'out'
        else:
            name = dirname[p+1:]
        # alter output name for output of static/shared library type
        if self.link_type == AutoMake.lo_static_library:
            name = 'lib' + name + '.a'
        elif self.link_type == AutoMake.lo_shared_library:
            name = 'lib' + name + '.so'
        return name

    def get_objects(self):
        """ Get objects of current project.
          Returns a dictionary of <object, source>
        """
        objs = {}
        for name in os.listdir(self.source_dir):
            parts = name.rsplit('.', 1)
            if len(parts) <= 1:
                continue
            if parts[1] in self.source_filter:
                objs[parts[0] + '.o'] = name
        return objs

    def get_object_files(self):
        return [self.object_dir + o for o in self.get_objects()]

    def get_output_file(self):
        return self.output_dir+self.get_output()

    def get_dependencies(self):
        """ Generate object dependency list by invoking compiler with '-MM' option.
        """
        deps = {}
        command = self.compiler + ' ' + self.includes + ' -MM ' + tostr(self.get_objects().values())
        with os.popen(command) as d:
            rlist = d.read().replace('\\\r\n', '').replace('\\\n', '').split('\n')
            for r in rlist:
                r.strip(' \t')
                if len(r) == 0:
                    continue
                flist = r.split(' ')
                deps[flist[0].rstrip(' :')] = flist[1:]
        return deps

    def compile(self, src, out, options=''):
        command = self.compiler + ' ' + options + ' -c ' + src + ' -o ' + out
        print(command)
        with os.popen(command) as d:
            print(d.read())

    def link(self):
        command = ''
        if self.link_type == AutoMake.lo_program:
            command = '%s %s -o %s %s' % \
                      (self.compiler, self.link_options, self.get_output_file(), tostr(self.get_object_files()))
        elif self.link_type == AutoMake.lo_shared_library:
            command = '%s %s -o %s %s' % \
                      (self.compiler, self.link_options, self.get_output_file(), tostr(self.get_object_files()))
        elif self.link_type == AutoMake.lo_static_library:
            command = 'ar %s %s %s' % \
                      (self.link_options, self.get_output(), tostr(self.get_object_files()))
        elif self.link_type == 'none':
            print('automake: nothing to do at link stage.')
            return
        else:
            print('automake error: unknown link type \'' + self.link_type + '\'.')
            exit(2)
        print(command)
        with os.popen(command) as d:
            print(d.read())

    @staticmethod
    def check_target(target, deps):
        if not exists(target):
            return False
        ts = os.stat(target).st_mtime
        for i in deps:
            if exists(i):
                ds = os.stat(i).st_mtime
                if ds > ts:
                    return False
        return True

    @staticmethod
    def ensure_dir(path):
        try:
            path = os.path.realpath(path)
            os.makedirs(path)
        except Exception:
            pass

    def build(self):
        objs = self.get_objects()
        deps = self.get_dependencies()
        # compile
        self.ensure_dir(self.object_dir)
        for (obj, src) in objs.items():
            target = self.object_dir + obj
            target_deps = [self.source_dir+src] + deps[obj][1:]
            if not self.check_target(target, target_deps):
                self.compile(src, target, self.compile_options)
        # link
        self.ensure_dir(self.output_dir)
        self.link()

    def clean(self):
        if self.link_type != AutoMake.lo_none:
            print('delete ' + self.get_output_file())
            rmfile(self.get_output_file())
        for o in self.get_object_files():
            print('delete ' + o)
            rmfile(o)


def getarg(argv, arg_switch, fallback=''):
    capture = False
    for a in argv:
        if capture:
            return a
        if a == arg_switch:
            capture = True
    return fallback


def getop(argv, fallback=''):
    if len(argv) > 1 and not argv[1].startswith('-'):
        return argv[1]
    return fallback


# main
if __name__ == '__main__':
    makefile = os.path.realpath(getarg(sys.argv, '-f', 'automake'))

    # change current working directory
    os.chdir(os.path.dirname(makefile))

    action = getop(sys.argv, 'build')

    automake = AutoMake()
    # creates a new automake file
    if action == 'create':
        automake.save(makefile)
        exit(0)

    if not os.path.isfile(makefile):
        print('automake error: automake file not found.')
        exit(1)

    try:
        automake.load(makefile)
        if action == 'build':
            automake.build()
        elif action == 'clean':
            automake.clean()
        else:
            print('automake error: unknown action \'' + action + '\'')
            exit(1)
    except Exception, e:
        print('automake error: ' + e.message)
        exit(5)

    exit(0)
