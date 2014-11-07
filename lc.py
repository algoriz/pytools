#
# Simple line count tool

import os
import sys
from os.path import *

def countfile(filename, filerule, verbose=True):
  if not filerule_test(filerule, filename):
    return 0
  l = 0
  with open(filename) as f:
    for ln in f:
      ln = ln.strip(' \r\n\t')
      if len(ln) != 0:
        l = l + 1
  if verbose:
    print(filename + (' :%d' % l))
  return l

def countdir(dirname, filerule, verbose=True):
  l = 0
  entries = os.listdir(dirname)
  for e in entries:
    p = join(dirname, e)
    l += count(p, filerule, verbose)
  if verbose:
    print('---- ' + dirname + (' %d' % l) + ' ----')
  return l

def count(path, filerule, verbose=True):
  ''' Count lines of a file or files in a directory '''
  if isfile(path):
    return countfile(path, filerule, verbose)
  return countdir(path, filerule, verbose)

def parse_filerule(str):
  ''' Parse file rules from a '/' separated string '''
  filerule = {}
  rules = str.split('/')
  for r in rules:
    r = r.strip(' \t')
    if len(r) == 0:
      continue
    if r[0] == '-':
      filerule[r[1:]] = False
    else:
      filerule[r] = True
  return filerule

def filerule_test(filerule, path):
  p = path.rfind('.')
  ext = '.'
  if p != -1:
    ext = path[p+1:]
  t = filerule.get(ext)
  return t == True or (t != False and filerule.get('*') == True)

default_filerule = 'c/cpp/cc/h/hh/hpp/cxx/java/py'

def help():
  print('Usage: lc.py <PATHs...> <--filerule={RULE1/RULE1/.../RULEn}> <--silent>')
  print('Example: lc.py mydir1 myfile2 --filerule=css/htm')
  print('  default file rule is: ' + default_filerule)
  print('  use . for files that has no extension name')
  print('  use * for any files that has an extension name')
  print('  use - prefix to exclude specific file types')

def lcmain(argv):
  if len(argv) <= 1:
    help()
    return 0
  
  verbose = True
  filerule = parse_filerule(default_filerule)
  for i in range(1, len(argv)):
    a = argv[i]
    if a.startswith('-'):
      if a == '--silent':
        verbose = False
      elif a.startswith('--filerule='):
        filerule = parse_filerule(a[len('--filerule='):])
      elif a == '-h' or a == '--help':
        help()
        return 0
      else:
        print('WARNING Unknown switch ignored: ' + a)

  lc = 0
  for i in range(1, len(argv)):
    a = argv[i]
    if not a.startswith('-'):
      lc += count(a, filerule, verbose)
  print(lc)
  exit(lc)

if __name__ == '__main__':
  lcmain(sys.argv)