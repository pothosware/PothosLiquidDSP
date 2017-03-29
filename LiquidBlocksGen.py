########################################################################
## Parse the liquid dsp header
########################################################################
import os
import sys
import re

sys.path.append(os.path.dirname(__file__))
import CppHeaderParser

def parseHeader(contents):

    #stop warning, lexer doesn't understand restrict
    contents = contents.replace('__restrict', '')

    #lexer can only handle C++ style structs
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

    return CppHeaderParser.CppHeader(contents, argType='string')

########################################################################
## Utilities for working with comments
########################################################################
def extractCommentBlock(lines, lastLine):
    while True:
        line = lines[lastLine]
        if not line.startswith('//'): break
        yield line[2:]
        lastLine -= 1

########################################################################
## Utilities for attribute extraction
########################################################################
class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__

def extractFunctionData(dataKey, blockData, myFilter, blockFunctions):
    keys = list()
    if dataKey in blockData:
        data = blockData[dataKey]
        try: keys.extend(data) #could be a list
        except: keys.append(data)
    elif myFilter is not None:
        for key, data in blockFunctions.items():
            if not myFilter(key): continue
            keys.append(key)

    results = list()
    for key in keys:
        data = blockFunctions[key]
        params = [AttributeDict(name=param['name'], type=param['type']) for param in data['parameters']]
        if dataKey != 'constructor': params = params[1:] #strip object for function calls
        paramTypesStr = ', '.join(['%s %s'%(param.type, param.name) for param in params])
        paramArgsStr = ', '.join([param.name for param in params])
        results.append(AttributeDict(
            key=key,
            name=data['name'],
            data=data,
            params=params,
            paramArgsStr=paramArgsStr,
            paramTypesStr=paramTypesStr))
    return results

def extractPorts(dataKey, prefix, blockData, blockFunctions):
    ports = list()
    for key, data in blockData[dataKey].items():
        key = str(key)
        param = data['param']
        fcnKey, argIdx = param.split(':')
        argIdx = int(argIdx)
        param = blockFunctions[fcnKey]['parameters'][argIdx]
        type = param['type']
        if param['pointer']: type = type.replace('*', '').strip()
        buffVar = prefix+key+'Buff'
        buffPass = buffVar if param['pointer'] else '*'+buffVar
        alias = None if 'alias' not in data else data['alias']
        reserve = None if 'reserve' not in data else data['reserve']
        ports.append(AttributeDict(
            key=key,
            portVar='_'+prefix+key,
            buffVar=buffVar,
            buffPass=buffPass,
            type=type,
            alias=alias,
            reserve=reserve,
            fcnKey=fcnKey,
            argIdx=argIdx))
    return ports

def extractWorker(blockData, blockFunctions, inputs, outputs):
    workData = blockData['work']
    fcnKey = workData['function']
    params = list()
    fcnData = blockFunctions[fcnKey]
    for argIdx, param in enumerate(fcnData['parameters']):
        if argIdx == 0: continue #skip object
        matches = [port for port in inputs + outputs if port.fcnKey == fcnKey and argIdx == port.argIdx]
        if len(matches) != 1: raise Exception('Cant find port match for %s[%d]'%(fcnKey, argIdx))
        params.append(matches[0])
    buffsStr = ', '.join([param.buffPass for param in params])
    return AttributeDict(
        fcnKey=fcnKey,
        fcnName=fcnData['name'],
        fcnData=fcnData,
        params=params,
        buffsStr=buffsStr,
        workData=workData,
        loop=workData.get('loop', False),
        decim=workData.get('decim', 1),
        interp=workData.get('interp', 1))

########################################################################
## Invoke the generator
########################################################################
from mako.template import Template

def generateCpp(blockName, blockData, headerData, contentsLines):

    blockFunctions = dict()
    for func in headerData.functions:
        if not func['name'].startswith(blockName+'_'): continue
        blockFunctions[func['name'].replace(blockName+'_', '')] = func

    constructor = extractFunctionData('constructor', blockData, lambda x: x == 'create', blockFunctions)[0]
    destructor = extractFunctionData('destructor', blockData, lambda x: x == 'destroy', blockFunctions)[0]
    initializers = extractFunctionData('initializers', blockData, None, blockFunctions)
    setters = extractFunctionData('setters', blockData, lambda x: x.startswith('set_'), blockFunctions)
    activators = extractFunctionData('activators', blockData, lambda x: x == 'reset', blockFunctions)
    inputs = extractPorts('inputs', 'in', blockData, blockFunctions)
    outputs = extractPorts('outputs', 'out', blockData, blockFunctions)

    #santy checks
    assert(constructor)
    assert(destructor)
    assert(inputs)
    assert(outputs)

    #work extraction
    worker = extractWorker(blockData, blockFunctions, inputs, outputs)

    tmpl_cpp = os.path.join(os.path.dirname(__file__), 'LiquidBlocks.tmpl.cpp')
    return Template(open(tmpl_cpp).read()).render(
        blockClass = blockName+'Block',
        blockName = blockName,
        constructor = constructor,
        destructor = destructor,
        initializers = initializers,
        activators = activators,
        setters = setters,
        inputs = inputs,
        outputs = outputs,
        worker = worker,
    )

########################################################################
## Generator entry point
########################################################################
import sys
import yaml

if __name__ == '__main__':
    liquidH = sys.argv[1]
    blocksYaml = sys.argv[2]
    outputCpp = sys.argv[3]

    #parse the header
    contentsH = open(liquidH).read()
    contentsLines = contentsH.splitlines()
    headerData = parseHeader(contentsH)

    #parse the blocks
    blocksData = yaml.load(open(blocksYaml).read())

    #run the generator
    output = ""
    for blockName, blockData in blocksData.items():
        output += generateCpp(blockName, blockData, headerData, contentsLines)
    open(outputCpp, 'w').write(output)
