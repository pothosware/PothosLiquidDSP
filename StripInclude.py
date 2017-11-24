import sys

out = ''
for line in open(sys.argv[1]).readlines():
    if line.strip().startswith('#include'): continue
    out += line

open(sys.argv[2], 'w').write(out)
