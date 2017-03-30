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
## Utilities for attribute extraction
########################################################################
class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__

def extractCommentBlock(lines, lastLine):
    while True:
        line = lines[lastLine]
        if not line.startswith('//'): break
        yield line[2:]
        lastLine -= 1

def extractBlockFunctions(blockName, headerData, commentLines):
    blockFunctions = dict()
    for func in headerData.functions:
        if not func['name'].startswith(blockName+'_'): continue
        func = AttributeDict([(k, v) for k, v in func.items()])
        func.docs = list(extractCommentBlock(contentsLines, func['line_number']-2))
        blockFunctions[func.name.replace(blockName+'_', '')] = func
    return blockFunctions

def extractFunctionData(dataKey, blockData, myFilter, blockFunctions):
    keys = list()
    if dataKey in blockData:
        data = blockData[dataKey]
        if isinstance(data, str): keys.append(data)
        if isinstance(data, list): keys.extend(data)
        if isinstance(data, dict): keys.extend(data.keys())
    elif myFilter is not None:
        for key, data in blockFunctions.items():
            if not myFilter(key): continue
            keys.append(key)

    defaultsData = blockData.get('defaults', {})
    results = list()
    for key in keys:
        data = blockFunctions[key]
        params = [AttributeDict(name=param['name'], type=param['type'], default=defaultsData.get(param['name'], None)) for param in data['parameters']]
        if dataKey != 'constructor': params = params[1:] #strip object for function calls
        if dataKey == 'constructor' and len(params) == 1 and params[0].type == 'void': params = [] #skip foo(void)

        internalParamsData = blockData.get('internalParams', {})
        externalParams = [p for p in params if p.name not in internalParamsData]
        paramTypesStr = ', '.join(['%s %s'%(param.type, param.name) for param in externalParams])
        paramArgsStr = ', '.join([param.name for param in params])

        results.append(AttributeDict(
            key=key,
            name=data.name,
            docs=data.docs,
            data=data,
            externalParams=externalParams,
            params=params,
            paramArgsStr=paramArgsStr,
            paramTypesStr=paramTypesStr))
    return results

def extractPorts(dataKey, prefix, blockData, blockFunctions):
    ports = list()
    portData = blockData[dataKey]
    workData = blockData['work']
    workArgs = workData['args']
    workFcn = workData['function']
    if isinstance(portData, str): portData = {portData:{}}
    for key, data in portData.items():
        key = str(key)
        fcnKey = workFcn
        argIdx = workArgs.index(key)+1
        param = blockFunctions[fcnKey]['parameters'][argIdx]
        type = param['type']
        if param['pointer']: type = type.replace('*', '').strip()
        portType = type
        if portType == 'liquid_float_complex': portType = 'std::complex<float>'
        if portType == 'liquid_double_complex': portType = 'std::complex<double>'
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
            portType=portType,
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
    funcArgs = list()
    for arg in workData['args']:
        matches = [port for port in inputs + outputs if port.key == arg]
        if not matches: funcArgs.append(arg)
        else: funcArgs.append(matches[0].buffPass)
    funcArgs = ', '.join(funcArgs)
    return AttributeDict(
        fcnKey=fcnKey,
        fcnName=fcnData['name'],
        fcnData=fcnData,
        params=params,
        funcArgs=funcArgs,
        workData=workData,
        loop=workData.get('loop', False),
        decim=workData.get('decim', 1),
        interp=workData.get('interp', 1))

########################################################################
## Invoke the generator
########################################################################
from mako.template import Template
import json
import re

def generateBlockDesc(blockName, blockData, constructor, initializers, setters):
    desc = dict()
    desc['name'] = blockData['name']
    desc['path'] = '/liquid/'+blockName
    desc['args'] = [param['name'] for param in constructor.params]
    desc['keywords'] = blockData.get('keywords', [])
    desc['categories'] = blockData.get('categories', [])
    desc['categories'].append('/Liquid DSP')

    desc['calls'] = list()
    for type, functions in [('initializer', initializers), ('setter', setters)]:
        for function in functions: desc['calls'].append(dict(
            type=type,
            name=function.key,
            args=[param.name for param in function.externalParams]))

    #param documentation mapping
    paramDocs = dict()
    for function in [constructor] + initializers + setters:
        for docline in function.docs:
            match = re.match('^\s*(\w+)\s*:\s*(.*)\s*$', docline)
            if match: paramDocs[match.groups()[0]] = [match.groups()[1]]

    desc['params'] = list()
    for function in [constructor] + initializers + setters:
        for param in function.externalParams:
            key = param.name
            desc['params'].append(dict(
                key=key,
                name=key.upper().replace('_', ' ').strip(),
                default=str(blockData.get('defaults', {}).get(key, '')),
                desc=paramDocs.get(key, [])))

    return json.dumps(desc)

def generateCpp(blockName, blockData, headerData, contentsLines):

    blockFunctions = extractBlockFunctions(blockName, headerData, contentsLines)
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

    #block desc
    blockDesc = generateBlockDesc(blockName, blockData, constructor, initializers, setters)
    blockDescEscaped = ''.join([hex(ord(ch)).replace('0x', '\\x') for ch in blockDesc])

    tmplCpp = os.path.join(os.path.dirname(__file__), 'LiquidBlocks.tmpl.cpp')
    return Template(open(tmplCpp).read()).render(
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
        blockDescEscaped = blockDescEscaped,
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
