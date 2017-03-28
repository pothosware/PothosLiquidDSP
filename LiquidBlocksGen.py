import os
import sys
import re

sys.path.append(os.path.dirname(__file__))
import CppHeaderParser

contents = open(sys.argv[1]).read()
contents = contents.replace('typedef struct', 'typedef')

#the lexer can only handle C++ style enums
s = 0
while True:
    s = contents.find('typedef enum', s)
    if s < 0: break
    e = contents.find(';', s)
    enum = contents[s:e]
    name = re.findall('\w+', enum, re.MULTILINE)[-1]
    contents = contents.replace(enum, enum.replace('typedef enum', 'enum %s'%name))
    s = e

header = CppHeaderParser.CppHeader(contents, argType='string')

def extractCommentBlock(lines, lastLine):
    out = list()
    while True:
        line = lines[lastLine]
        if not line.startswith('//'): break
        out.insert(0, line[2:])
        lastLine -= 1
    return out

print dir(header)
#print header.typedefs
#print header.enums
for func in header.functions:
    if 'iirdes_dzpk2sosf' == func['name']:
        print func.keys()
        print '\n'.join(extractCommentBlock(contents.splitlines(), func['line_number']-2))
