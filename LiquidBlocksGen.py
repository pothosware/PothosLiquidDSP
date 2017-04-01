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

    #the lexer will consume comments as doxygen
    contents = contents.replace('//', '//!')
    contents = contents.replace('/*', '/*!')

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

def extractBlockFunctions(blockName, headerData, commentLines):
    blockFunctions = dict()
    for func in headerData.functions:
        if not func['name'].startswith(blockName+'_'): continue
        func = AttributeDict([(k, v) for k, v in func.items()])
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
            docs=data.get('doxygen', ''),
            data=data,
            rtnType=data.rtnType,
            externalParams=externalParams,
            params=params,
            paramArgsStr=paramArgsStr,
            paramTypesStr=paramTypesStr))
    return results

def extractWorkCalls(blockData):
    calls = list()
    workCalls = blockData['work']['calls']
    if isinstance(workCalls, str): workCalls = [workCalls]

    for workCall in workCalls:
        m = re.match('(\w+)\((.+)\)', workCall)
        name = m.groups()[0]
        args = m.groups()[1].split(',')
        args = map(str.strip, args)
        calls.append((name, args))

    return calls

def extractPorts(dataKey, prefix, blockData, blockFunctions):
    ports = list()
    portData = blockData[dataKey]
    workCalls = extractWorkCalls(blockData)
    if isinstance(portData, str): portData = {portData:{}}
    for key, data in portData.items():
        key = str(key)
        argIdx = None
        for workFcn, workArgs in workCalls:
            try:
                argIdx = workArgs.index(key)+1
                fcnKey = workFcn
            except: pass
        assert(argIdx is not None)
        param = blockFunctions[fcnKey]['parameters'][argIdx]
        type = param['type']
        if param['pointer']: type = type.replace('*', '').strip()
        portType = type
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
    workCalls = extractWorkCalls(blockData)
    functions = list()
    for workFcn, workArgs in workCalls:
        fcnData = blockFunctions[workFcn]
        funcArgs = list()
        for arg in workArgs:
            matches = [port for port in inputs + outputs if port.key == arg]
            if not matches: funcArgs.append(arg)
            else: funcArgs.append(matches[0].buffPass)
        functions.append(AttributeDict(name=fcnData['name'], args=', '.join(funcArgs)))
    return AttributeDict(
        functions=functions,
        mode=workData.get('mode', 'STANDARD_LOOP'),
        factor=workData.get('factor', 1),
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
        for docline in function.docs.splitlines():
            if '/*!' in docline:
                for comment in docline.split('/*!'):
                    match = re.match('^\s*(\w+)\s*:\s*(.*)\s*\*/', comment)
                    if match: paramDocs[match.groups()[0]] = match.groups()[1]
            elif '//!' in docline:
                for comment in docline.split('//!'):
                    match = re.match('^\s*(\w+)\s*:\s*(.*)\s*$', comment)
                    if match: paramDocs[match.groups()[0]] = match.groups()[1]
    #for key, data in paramDocs.items(): print key, data

    desc['params'] = list()
    for function in [constructor] + initializers + setters:
        for param in function.externalParams:

            #skip duplicates also found in the constructor
            if function != constructor and param in constructor.externalParams: continue

            key = param.name
            name = key.replace('_', ' ').strip()
            units = None

            #remove db from units
            if name.lower().endswith('db'):
                name = name[:-2].strip()
                units = 'dB'

            #generate a displayable name
            name = name.title() if len(name) > 3 else name.upper()

            data = dict(
                key=key,
                name=name,
                default=str(blockData.get('defaults', {}).get(key, '')))

            #apply units if set already
            if units: data['units'] = units

            #apply docs if found
            if key in paramDocs:
                data['desc'] = [paramDocs[key]]
                match = re.match('.*\[(.*)\]', paramDocs[key])
                if match: data['units'] = match.groups()[0]

            desc['params'].append(data)

    return desc

def generateCpp1(blockKey, blockName, blockData, headerData, contentsLines):

    blockFunctions = extractBlockFunctions(blockKey, headerData, contentsLines)
    constructor = extractFunctionData('constructor', blockData, lambda x: x == 'create', blockFunctions)[0]
    destructor = extractFunctionData('destructor', blockData, lambda x: x == 'destroy', blockFunctions)[0]
    initializers = extractFunctionData('initializers', blockData, None, blockFunctions)
    setters = extractFunctionData('setters', blockData, lambda x: x.startswith('set_'), blockFunctions)
    getters = extractFunctionData('getters', blockData, lambda x: x.startswith('get_'), blockFunctions)
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

    #C++ class
    blockClassTmplCpp = os.path.join(os.path.dirname(__file__), 'tmpl', 'LiquidBlockClass.tmpl.cpp')
    tmplData = AttributeDict(
        blockClass = blockName+'Block',
        blockName = blockName,
        constructor = constructor,
        destructor = destructor,
        initializers = initializers,
        activators = activators,
        setters = setters,
        getters = getters,
        inputs = inputs,
        outputs = outputs,
        worker = worker)
    outCpp = Template(open(blockClassTmplCpp).read()).render(**tmplData)

    return outCpp, blockDesc, tmplData

def generateCpp(blockName, blockData, headerData, contentsLines):

    blockKey = blockData.get('key', blockName)
    subtypes = blockData.get('subtypes', [])
    factoryArgs = list()
    subtypesArgs = list()

    #generate class for every subtype
    blockClassesCpp = ""
    if subtypes:
        for subtype in subtypes:
            outCpp, blockDesc, tmplData = generateCpp1(blockKey + '_' + subtype, blockName + '_' + subtype, blockData, headerData, contentsLines)
            blockClassesCpp += outCpp
            constructor = tmplData.constructor
            subtypeFactoryArgs = ['o%d.convert<%s>()'%(i, p.type) for i, p in enumerate(constructor.externalParams)]
            subtypeFactoryArgs = ', '.join(subtypeFactoryArgs)
            subfactory = tmplData.blockClass
            subtypesArgs.append((subtype, subfactory, subtypeFactoryArgs))

        factory = 'make'+blockName+'Block'
        factoryArgs = ['const std::string &type'] + ['const Pothos::Object &o%d'%i for i in range(len(blockDesc['args']))]
        factoryArgs = ', '.join(factoryArgs)

        #add subtypes to blockDesc
        typeParam = dict(
            name = 'Type',
            key = 'type',
            desc = ['Select block data types'],
            preview = 'disable',
            options = [dict(name=s.upper(), value='"%s"'%s) for s in subtypes])
        blockDesc['params'].insert(0, typeParam)
        blockDesc['args'].insert(0, 'type')
        blockDesc['path'] = '/liquid/'+blockName

    #or just the single block entry
    else:
        outCpp, blockDesc, tmplData = generateCpp1(blockKey, blockName, blockData, headerData, contentsLines)
        factory = tmplData.blockClass+'::make'
        blockClassesCpp += outCpp

    #encode the block description into escaped JSON
    blockDescEscaped = ''.join([hex(ord(ch)).replace('0x', '\\x') for ch in json.dumps(blockDesc)])

    #complete C++ source
    registrationTmplCpp = os.path.join(os.path.dirname(__file__), 'tmpl', 'LiquidRegistration.tmpl.cpp')
    outCpp = Template(open(registrationTmplCpp).read()).render(
        blockClass = blockName+'Block',
        blockName = blockName,
        factory = factory,
        factoryArgs = factoryArgs,
        subtypesArgs = subtypesArgs,
        blockClasses = blockClassesCpp,
        blockDescEscaped = blockDescEscaped)

    return outCpp

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
