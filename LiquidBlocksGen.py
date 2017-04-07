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
    #it comes from the #include <inttypes.h>
    contents = contents.replace('__restrict', '')

    #add newlines lost from macro expansion back into the /**/ comments
    #to ensure that the docs get associated with the proceeding function
    contents = contents.replace('/*', '\n/*')
    contents = contents.replace('*/', '*/\n')

    #the lexer will consume comments as doxygen (add ! to trigger this)
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

def extractDocumentation(data):
    doxygen = data.get('doxygen', '')
    for line in doxygen.splitlines():
        for tok in line.split('/*!'):
            tok = tok.split('*/')[0]
            tok = tok.split('//!')[-1]
            tok = tok.strip()
            if tok: yield(tok)

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

    def getParamType(p):
        typemaps = blockData.get('typemaps', {})
        if p['name'] not in typemaps: return p['type']
        oldType = p['type']
        newType = typemaps[p['name']]
        if p['pointer']: oldType = oldType.replace('*', '').strip()
        return newType.replace('T', oldType)

    def paramToLiquidArg(param):
        #we know liquid uses pointers, not vectors
        #write the type mapping back into a pointer
        if 'std::vector' in param.type:
            return param.name + '.data()'
        return param.name

    defaultsData = blockData.get('defaults', {})
    internalsData = blockData.get('internals', {})
    results = list()
    for key in keys:
        data = blockFunctions[key]
        getDefault = lambda p: defaultsData.get(param['name'], internalsData.get(param['name'], param['name'] if dataKey == 'constructor' else None))
        params = [AttributeDict(name=param['name'], type=getParamType(param), default=getDefault(param)) for param in data['parameters']]
        if dataKey != 'constructor': params = params[1:] #strip object for function calls
        if dataKey == 'constructor' and len(params) == 1 and params[0].type == 'void': params = [] #skip foo(void)

        externalParams = [p for p in params if p.name not in internalsData]
        paramTypesStr = ', '.join(['%s %s'%(param.type, param.name) for param in externalParams])
        passArgsStr = ', '.join([param.name for param in externalParams])
        paramArgsStr = ', '.join(map(paramToLiquidArg, params))

        results.append(AttributeDict(
            key=key,
            name=data.name,
            doclines=extractDocumentation(data),
            data=data,
            rtnType=data.rtnType,
            externalParams=externalParams,
            params=params,
            paramArgsStr=paramArgsStr,
            passArgsStr=passArgsStr,
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

def generateBlockDesc(blockName, blockData, headerData, constructor, initializers, setters):
    desc = dict()
    desc['name'] = blockData['name']
    desc['path'] = '/liquid/'+blockName
    desc['args'] = [param['name'] for param in constructor.externalParams]
    desc['keywords'] = blockData.get('keywords', [])
    desc['categories'] = blockData.get('categories', [])
    desc['categories'].append('/Liquid DSP')

    desc['calls'] = list()
    for type, functions in [('initializer', initializers), ('setter', setters)]:
        for function in functions: desc['calls'].append(dict(
            type=type,
            name=function.key,
            args=[param.name for param in function.externalParams]))

    #enum mapping
    enums = dict([(enum['name'], enum) for enum in headerData.enums])

    #param documentation mapping
    blockDocs = list()
    paramDocs = dict()
    for function in [constructor] + initializers + setters:
        for docline in function.doclines:
            match = re.match('^\s*(\w+)\s*:\s*(.*)\s*$', docline)
            if match: paramDocs[match.groups()[0]] = match.groups()[1]
            elif function == constructor: blockDocs.append(docline)
            if docline.count('(') != docline.count(')') or \
                docline.count('[') != docline.count(']') or \
                docline.count('{') != docline.count('}'):
                print('Warning: bracket mismatch %s: "%s"'%(function.name, docline))
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
            else:
                print('Warning: missing documentation for %s(%s)'%(function.name, key))

            #enumerated options
            if param.type in enums:
                data['default'] = '"%s"'%data['default']
                data['options'] = [dict(value='"%s"'%value['name'], name=value['name']) for value in enums[param.type]['values']]

            desc['params'].append(data)

    desc['docs'] = blockDocs
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
    blockDesc = generateBlockDesc(blockName, blockData, headerData, constructor, initializers, setters)

    #C++ class
    blockClassTmplCpp = os.path.join(os.path.dirname(__file__), 'tmpl', 'LiquidBlockClass.tmpl.cpp')
    tmplData = AttributeDict(
        blockClass = 'liquid_'+blockName+'_block',
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

def generateCpp(resourceName, blockName, blockData, headerData, contentsLines):

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

        factory = 'make_liquid_'+blockName+'_block'
        factoryArgs = ['const std::string &type'] + ['const Pothos::Object &o%d'%i for i in range(len(blockDesc['args']))]
        factoryArgs = ', '.join(factoryArgs)

        #add subtypes to blockDesc
        typeParam = dict(
            name = 'Data Types',
            key = 'dtype',
            desc = ['Select block data types'],
            preview = 'disable',
            options = [dict(name=s.upper(), value='"%s"'%s) for s in subtypes])
        blockDesc['params'].insert(0, typeParam)
        blockDesc['args'].insert(0, 'dtype')
        blockDesc['path'] = '/liquid/'+blockName

    #or just the single block entry
    else:
        outCpp, blockDesc, tmplData = generateCpp1(blockKey, blockName, blockData, headerData, contentsLines)
        factory = tmplData.blockClass+'::make'
        blockClassesCpp += outCpp

    #refererence url
    url = 'http://liquidsdr.org/doc/%s/'%resourceName
    blockDesc['docs'].append('<br/>Reference: <a href="%s">%s</a>'%(url, url))

    #encode the block description into escaped JSON
    blockDescEscaped = ''.join([hex(ord(ch)).replace('0x', '\\x') for ch in json.dumps(blockDesc)])

    #complete C++ source
    registrationTmplCpp = os.path.join(os.path.dirname(__file__), 'tmpl', 'LiquidRegistration.tmpl.cpp')
    outCpp = Template(open(registrationTmplCpp).read()).render(
        blockClass = 'liquid_'+blockName+'_block',
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
    resourceIn = sys.argv[2]
    outputDest = sys.argv[3]

    #parse the header
    contentsH = open(liquidH).read()
    contentsLines = contentsH.splitlines()
    headerData = parseHeader(contentsH)

    if resourceIn == "ENUMS":
        enumsTmplCpp = os.path.join(os.path.dirname(__file__), 'tmpl', 'LiquidEnums.tmpl.cpp')
        output = Template(open(enumsTmplCpp).read()).render(enums=headerData.enums)
        open(outputDest, 'w').write(output)

    else:

        #parse the blocks
        resourceName =  os.path.splitext(os.path.basename(resourceIn))[0]
        blocksData = yaml.load(open(resourceIn).read())

        #run the generator
        output = ""
        for blockName, blockData in blocksData.items():
            output += generateCpp(resourceName, blockName, blockData, headerData, contentsLines)
        open(outputDest, 'w').write(output)
