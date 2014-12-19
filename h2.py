#!/usr/bin/python

import os
import sys
import platform
import json
import subprocess

from os.path import exists


def tocsv(items, sep=' '):
    """ Converts a list into a CSV string.
      :param items: The list to be converted
      :param sep: The string used to separate the values
      :returns: The composed CSV string.
    """
    values = ''
    for i in items:
        values += i
        values += sep
    return values[:-len(sep)]


def remove(path):
    """ Removes a file. If something is wrong, such as the file is not found,
      this method doesn't raise any exception.
    :param path: Path to the file to be removed.
    :return: nothing
    """
    try:
        os.remove(path)
    except Exception:
        pass


def get(dictionary, key, fallback=None):
    """ Get the value associated with the key from dict.
      If the key doesn't exist in dict, the fallback value is returned.
    """
    if key in dictionary:
        return dictionary[key]
    return fallback


def dirfix(dir):
    if dir != '' and not dir.endswith('/'):
        return dir + '/'
    return dir


def getarg(argv, arg_switch, fallback=''):
    capture = False
    for a in argv:
        if capture:
            return a
        if a == arg_switch:
            capture = True
    return fallback


class CurrentSystem:
    PLATFORM_NAME = platform.system()

    def __init__(self):
        pass

    @staticmethod
    def is_windows():
        return CurrentSystem.PLATFORM_NAME == 'Windows'

    @staticmethod
    def is_macintosh():
        return CurrentSystem.PLATFORM_NAME == 'Darwin'

    @staticmethod
    def is_linux():
        return CurrentSystem.PLATFORM_NAME == 'Linux'

    @staticmethod
    def compiler():
        if CurrentSystem.is_windows():
            # For Windows, default compiler is VC++ compiler 'cl.exe'
            return 'cl.exe'
        elif CurrentSystem.is_macintosh():
            # For MacOS, default compiler is 'clang++'
            return 'clang++'
        else:
            # For other OS's, default compiler is 'g++'
            return 'g++'

    @staticmethod
    def static_lib(name):
        if CurrentSystem.is_windows():
            return name + '.lib'
        else:
            return 'lib' + name + '.a'

    @staticmethod
    def shared_lib(name):
        if CurrentSystem.is_windows():
            return name + '.dll'
        else:
            return 'lib' + name + '.so'


class HydrogenMake:
    PLATFORM_NAME = platform.system()
    # linkage types
    LINK_STATIC_LIBRARY = 'static'
    LINK_PROGRAM = 'program'
    LINK_SHARED_LIBRARY = 'shared'
    LINK_NONE = 'none'
    # default properties
    # NOTE that relative paths are relative to the directory that containing the m2 file
    DEFAULT_SOURCE_DIR = './'
    DEFAULT_OBJECT_DIR = '../obj/'
    DEFAULT_OUTPUT_DIR = '../out/'
    DEFAULT_HEADER_FILTERS = ['h', 'hh', 'hpp', None]
    DEFAULT_SOURCE_FILTERS = ['cc', 'c', 'cxx', 'cpp']

    def __init__(self):
        self.module_name = ''       # module name
        self.source_dir = ''        # path to source file directory
        self.object_dir = ''        # path to object file directory
        self.output_dir = ''        # path to output file directory
        self.output_name = ''       # name of module output, if left empty a deduced name will be used
        self.compiler = ''          # compiler used to make the module
        self.compile_options = ''   # options passed to the compiler
        self.includes = ''          # header locations passed to the compiler, e.g. '-I./'
        self.link_options = ''      # options passed to the linker
        self.link_type = ''         # module linkage type, could be one of 'static', 'shared', 'program' or 'none'
        self.header_filters = None  # header file extensions
        self.source_filters = None  # source file extensions

    def log(self, message):
        print('h2 ' + self.module_name + ': ' + message)

    def err(self, message):
        self.log('ERROR ' + message)
        exit(1)

    def set_essential_defaults(self):
        """ Set default module properties """
        if self.source_dir == '':
            self.source_dir = './'
        elif not self.source_dir.endswith('/'):
            self.source_dir += '/'
        if self.module_name == '':
            # deduce module name from source dir name
            source_path = os.path.realpath(self.source_dir)
            if source_path.endswith('/'):
                source_path = source_path[:-1]
            p = source_path.rfind('/')
            if p == -1:
                self.module_name = 'out'
            else:
                self.module_name = source_path[p+1:]
            self.log('using default module name: ' + self.module_name)
        if self.compiler == '':
            self.compiler = CurrentSystem.compiler()
            self.log('using default compiler: ' + self.compiler)
        if self.link_type == '':
            self.link_type = HydrogenMake.LINK_PROGRAM
            self.log('using default link_type: ' + self.link_type)
        if self.object_dir == '':
            self.object_dir = HydrogenMake.DEFAULT_OBJECT_DIR
            self.log('using default object_dir: ' + self.object_dir)
        if self.output_dir == '':
            self.output_dir = HydrogenMake.DEFAULT_OUTPUT_DIR
            self.log('using default output_dir: ' + self.output_dir)
        if self.includes == '':
            self.includes = '-I./'
            self.log('using default includes: ' + self.includes)
        if self.header_filters is None:
            self.header_filters = HydrogenMake.DEFAULT_HEADER_FILTERS
            self.log('using default header_filters: ' + json.dumps(self.header_filters))
        if self.source_filters is None:
            self.source_filters = HydrogenMake.DEFAULT_SOURCE_FILTERS
            self.log('using default source_filters: ' + json.dumps(self.source_filters))

    def save(self, name=None):
        """ Save configurations to the file. """
        if name is None:
            return json.dumps(self.__dict__, indent=True)
        else:
            json.dump(self.__dict__, open(name, 'w'), indent=True)

    def load(self, name):
        """ Load configurations from file. """
        d = json.load(open(name))
        self.module_name = get(d, 'module_name', '').strip(' \t\n\r')
        self.source_dir = dirfix(get(d, 'source_dir', ''))
        self.object_dir = dirfix(get(d, 'object_dir', ''))
        self.output_dir = dirfix(get(d, 'output_dir', ''))
        self.output_name = get(d, 'output_name', '').strip(' \t\n\r')
        self.compiler = get(d, 'compiler', '').strip(' \t\n\r')
        self.compile_options = get(d, 'compile_options', '')
        self.link_options = get(d, 'link_options', '')
        self.link_type = get(d, 'link_type', '')
        self.includes = get(d, 'includes', '')
        self.header_filters = get(d, 'header_filters', None)
        self.source_filters = get(d, 'source_filters', None)
        self.set_essential_defaults()

    def module_sources(self):
        """ List of module source names. """
        sources = []
        for name in os.listdir(self.source_dir):
            parts = name.rsplit('.', 1)
            extension = None
            if len(parts) > 1:
                extension = parts[1]
            if extension in self.source_filters:
                sources.append(name)
        return sources

    def module_source_files(self):
        """ List of module source files. """
        return [self.source_dir + src for src in self.module_sources()]

    def module_output(self):
        """ Module output name. """
        if len(self.output_name) != 0:
            return self.output_name

        if self.link_type == HydrogenMake.LINK_STATIC_LIBRARY:
            return CurrentSystem.static_lib(self.module_name)
        elif self.link_type == HydrogenMake.LINK_SHARED_LIBRARY:
            return CurrentSystem.shared_lib(self.module_name)
        elif self.link_type == HydrogenMake.LINK_NONE:
            return ''
        return self.module_name

    def module_output_file(self):
        """ Module output file. """
        output = self.module_output()
        if len(output):
            output = self.output_dir + output
        return output

    def module_objects(self):
        """ List of module object names. """
        objects = []
        for name in os.listdir(self.source_dir):
            parts = name.rsplit('.', 1)
            extension = None
            if len(parts) > 1:
                extension = parts[1]
            if extension in self.source_filters:
                objects.append(parts[0] + '.o')
        return objects

    def module_object_files(self):
        """ List of module object files. """
        return [self.object_dir + o for o in self.module_objects()]

    def object_dependency_map(self):
        """ Generate object dependency map by invoking compiler with '-MM' option. """
        m = {}
        source_files = self.module_source_files()
        command = self.compiler + ' ' + self.includes + ' -MM ' + tocsv(source_files)
        out = self.execute(command, echo=False, silent=True)
        rules = out.replace('\\\r\n', '').replace('\\\n', '').replace('\\\r', '').split('\n')
        for r in rules:
            r.strip(' \t\r\n')
            if len(r) == 0:
                continue
            # g++ -MM file.cc
            # file.o: file.cc file.h <...dependent.h>
            # NOTE that spaces are not allowed in file names
            files = r.split(' ')
            m[self.object_dir + files[0].rstrip(' :')] = files[1:]
        # validate dependency map
        if len(m) < len(source_files):
            self.err('unexpected object dependency information generated by compiler: ' + out)
        return m

    def execute(self, command, echo=True, silent=False, exit_on_fail=True):
        """ Executes a command and returns command output. """
        if echo:
            self.log(command)
        try:
            output = subprocess.check_output(command, shell=True)
        except subprocess.CalledProcessError, e:
            output = e.output
            if not silent and len(output):
                self.log(output)
            if exit_on_fail:
                self.log('*** FATAL ERROR, STOPPED ***')
                exit(e.returncode)
        return output

    def compile(self, src, out, do_compile=True):
        command = self.compiler + ' ' + self.compile_options + ' ' + self.includes + ' -c ' + src + ' -o ' + out
        if do_compile:
            self.execute(command)
        return command

    def link(self, do_link=True):
        command = ''
        if self.link_type == HydrogenMake.LINK_PROGRAM:
            command = '%s %s -o %s %s' % \
                      (self.compiler, self.link_options, self.module_output_file(), tocsv(self.module_object_files()))
        elif self.link_type == HydrogenMake.LINK_SHARED_LIBRARY:
            command = '%s %s -o %s %s' % \
                      (self.compiler, self.link_options, self.module_output_file(), tocsv(self.module_object_files()))
        elif self.link_type == HydrogenMake.LINK_STATIC_LIBRARY:
            command = 'ar -r %s %s %s' % \
                      (self.link_options, self.module_output_file(), tocsv(self.module_object_files()))
        elif self.link_type == HydrogenMake.LINK_NONE:
            pass
        else:
            self.err('unknown link type \'' + self.link_type + '\'.')
        if do_link:
            self.execute(command)
        return command

    @staticmethod
    def check_target(target, dependencies):
        if not exists(target):
            return False
        ts = os.stat(target).st_mtime
        for item in dependencies:
            if exists(item):
                ds = os.stat(item).st_mtime
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
        # compile
        objects = self.object_dependency_map()
        recompiled = False
        self.ensure_dir(self.object_dir)
        for (obj, dependencies) in objects.items():
            if not self.check_target(obj, dependencies):
                self.compile(dependencies[0], obj)
                recompiled = True
        # link
        relinked = False
        if self.link_type != 'none':
            self.ensure_dir(self.output_dir)
            output = self.module_output_file()
            objects = self.module_object_files()
            if not self.check_target(output, objects):
                self.link()
                relinked = True
        if not recompiled and not relinked:
            self.log('all targets are up to date.')

    def clean(self):
        if self.link_type != HydrogenMake.LINK_NONE:
            output = self.module_output_file()
            remove(output)
        for o in self.module_object_files():
            remove(o)

    def dump_make(self):
        print('# This makefile is generated by h2 (https://github.com/algoriz/pytools)')
        # build section
        has_output = self.link_type != HydrogenMake.LINK_NONE
        if has_output:
            print('build: prebuild ' + self.module_output_file())
            print('')
            print(self.module_output_file() + ': ' + tocsv(self.module_object_files()))
            print('\t' + self.link(do_link=False))
        else:
            print('build: prebuild' + tocsv(self.module_object_files()))
        print('')
        objects = self.object_dependency_map()
        for (obj, dependencies) in objects.items():
            print(obj + ': ' + tocsv(dependencies))
            print('\t' + self.compile(dependencies[0], obj, do_compile=False))
        print('')

        # init section
        print('prebuild:')
        if has_output:
            print('\t@mkdir -p ' + self.output_dir)
        print('\t@mkdir -p ' + self.object_dir)
        print('')

        # clean section
        print('clean:')
        print('\t@-rm -f ' + tocsv(self.module_object_files()))
        if has_output:
            print('\t@-rm -f ' + self.module_output_file())
        print('')


def print_help():
    print('h2 is a tool helps to automate the build process of a C++ module.')
    print('usage: h2 <action> <OPTIONS>')
    print('  action may be one of:')
    print('    build   build the module, this is the default action')
    print('    clean   clean output and object files')
    print('    create  creates a new module properties file')
    print('    detail  display module properties')
    print('    export  export build process as makefile')
    print('  available options are:')
    print('    -f <file>  specifies the properties file for the module.')
    print('               h2 searches current directory for \'h2.properties\' by default.')
    print('')
    print('    -h         prints this help message')


# main
if __name__ == '__main__':
    if '-h' in sys.argv:
        print_help()
        exit(0)
    # the h2 properties file
    h2prop = os.path.realpath(getarg(sys.argv, '-f', 'h2.properties'))
    # cd to the directory that contains the properties file
    os.chdir(os.path.dirname(h2prop))

    action = 'build'
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        action = sys.argv[1]

    h2 = HydrogenMake()
    if action == 'create':
        # guess module name
        h2.module_name = os.path.basename(h2prop).split('.', 1)[0]
        if h2.module_name == 'h2':
            h2.module_name = ''
        h2.set_essential_defaults()
        h2.save(h2prop)
        print('h2 properties file saved to ' + os.path.basename(h2prop))
        exit(0)

    if not os.path.isfile(h2prop):
        print('file ' + h2prop + ' not found.')
        exit(1)

    try:
        h2.load(h2prop)
        if action == 'build':
            h2.build()
        elif action == 'clean':
            h2.clean()
        elif action == 'detail':
            print(h2.save())
        elif action == 'export':
            h2.dump_make()
        else:
            print('unknown action \'' + action + '\'')
            exit(4)
    except Exception, e:
        print('exception caught \'' + e.message + '\'')
        exit(5)

    exit(0)
