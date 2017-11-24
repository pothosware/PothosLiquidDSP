########################################################################
## Logger output
########################################################################
HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'

#try to use colorama to support ANSI color codes on windows
try:
    from colorama import init
    init()
except ImportError: pass

LOG = [""]

import sys
def header(msg, *args): sys.stderr.write(HEADER+msg%args+"\n"+ENDC);    LOG[0]+=msg%args+"\n"
def notice(msg, *args): sys.stderr.write(OKGREEN+msg%args+"\n"+ENDC);   LOG[0]+="I: "+msg%args+"\n"
def warning(msg, *args): sys.stderr.write(WARNING+msg%args+"\n"+ENDC);  LOG[0]+="W: "+msg%args+"\n"
def error(msg, *args): sys.stderr.write(FAIL+msg%args+"\n"+ENDC);       LOG[0]+="E: "+msg%args+"\n"
def blacklist(msg, *args): sys.stderr.write(OKBLUE+msg%args+"\n"+ENDC); LOG[0]+="B: "+msg%args+"\n"

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

def extractBlockFunctions(blockName, headerData):
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
    externalsData = blockData.get('externals', {})
    results = list()
    for key in keys:
        data = blockFunctions[key]
        getDefault = lambda p: defaultsData.get(p['name'], internalsData.get(p['name'], p['name'] if dataKey == 'constructor' else None))
        params = [AttributeDict(name=param['name'], type=getParamType(param), default=getDefault(param)) for param in data['parameters']]
        for extParamName, extParamType in externalsData.items():
            params.append(AttributeDict(name=extParamName, type=extParamType, default=extParamName))
        if dataKey != 'constructor': params = params[1:] #strip object for function calls
        if dataKey == 'constructor' and len(params) == 1 and params[0].type == 'void': params = [] #skip foo(void)

        externalParams = [p for p in params if p.name not in internalsData]
        internalParams = [p for p in params if p.name not in externalsData]
        paramTypesStr = ', '.join(['%s %s'%(param.type, param.name) for param in externalParams])
        passArgsStr = ', '.join([param.name for param in externalParams])
        paramArgsStr = ', '.join(map(paramToLiquidArg, internalParams))

        results.append(AttributeDict(
            key=key,
            name=data.name,
            doclines=list(extractDocumentation(data)),
            data=data,
            returns=data.returns,
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
        m = re.match('((\w+)\s*=\s*)?(\w+)\((.+)\)', workCall)
        ret = m.groups()[1]
        name = m.groups()[2]
        args = m.groups()[3].split(',')
        args = list(map(str.strip, args))
        calls.append((ret, name, args))

    return calls

def extractPorts(dataKey, prefix, blockData, blockFunctions):
    ports = list()
    portData = blockData[dataKey]
    workCalls = extractWorkCalls(blockData)
    if isinstance(portData, str): portData = {portData:{}}
    for key, data in portData.items():
        key = str(key)
        argIdx = None
        for workRet, workFcn, workArgs in workCalls:
            if workRet == key:
                argIdx = -1
                fcnKey = workFcn
            try:
                argIdx = workArgs.index(key)+1
                fcnKey = workFcn
            except: pass
        assert(argIdx is not None)
        if argIdx == -1: param = dict(
            pointer=blockFunctions[fcnKey]['returns_pointer'],
            type=blockFunctions[fcnKey]['returns'])
        else:
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
    for workRet, workFcn, workArgs in workCalls:
        fcnData = blockFunctions[workFcn]
        funcArgs = list()
        for arg in workArgs:
            matches = [port for port in inputs + outputs if port.key == arg]
            if matches: funcArgs.append(matches[0].buffPass)
            else: funcArgs.append(arg)
        name = fcnData['name']
        if workRet is not None:
            matches = [port for port in inputs + outputs if port.key == workRet]
            if matches: name = '%s = %s'%(matches[0].buffPass, name)
            else: name = '%s = %s'%(workRet, name)
        functions.append(AttributeDict(name=name, args=', '.join(funcArgs)))
    return AttributeDict(
        functions=functions,
        mode=workData.get('mode', 'STANDARD_LOOP'),
        factor=workData.get('factor', 1),
        decim=workData.get('decim', 1),
        interp=workData.get('interp', 1))

def extractSubtypes(blockKey, headerData):
    blockNames = extractBlockFunctions(blockKey, headerData).keys()
    subtypes = dict()
    for fullName in blockNames:
        if '_' not in fullName: return list()
        subkey, name = fullName.split('_', 1)
        if subkey not in subtypes: subtypes[subkey] = set()
        subtypes[subkey].add(name)

    values0 = subtypes[list(subtypes)[0]]
    for subkey, values in subtypes.items():
        if values != values0: return list()

    return subtypes.keys()

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
    desc['categories'] = ['/LiquidDSP'+c for c in blockData.get('categories', ['/Misc'])]

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
            if docline.count('(')+docline.count('[') != \
                docline.count(')')+docline.count(']') or \
                docline.count('{') != docline.count('}'):
                warning('Bracket mismatch %s: "%s"'%(function.name, docline))

    #missing format, but there is only one line and one parameter
    for function in initializers + setters:
        if len(function.params) != 1: continue
        if function.params[0].name in paramDocs: continue
        if len(function.doclines) != 1: continue
        paramDocs[function.params[0].name] = function.doclines[0]

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
                warning('Missing documentation for %s(%s)'%(function.name, key))

            #enumerated options
            if param.type in enums:
                data['default'] = '"%s"'%data['default']
                data['options'] = [dict(value='"%s"'%value['name'], name=value['name']) for value in enums[param.type]['values']]

            desc['params'].append(data)

    desc['docs'] = blockDocs
    return desc

def generateCpp1(blockKey, blockName, blockData, headerData, contentsLines):

    blockFunctions = extractBlockFunctions(blockKey, headerData)
    constructor = extractFunctionData('constructor', blockData, lambda x: x == 'create', blockFunctions)[0]
    destructor = extractFunctionData('destructor', blockData, lambda x: x == 'destroy', blockFunctions)[0]
    initializers = extractFunctionData('initializers', blockData, None, blockFunctions)
    setters = extractFunctionData('setters', blockData, lambda x: x.startswith('set_'), blockFunctions)
    getters = extractFunctionData('getters', blockData, lambda x: x.startswith('get_'), blockFunctions)
    getters = [g for g in getters if not g.params] #cant handle getters with pointers for outputs yet
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

def generateCpp(resourceName, blockName, blockData, headerData, contentsLines, siteInfo):

    docKey = blockData.get('doc', resourceName)
    blockKey = blockData.get('key', blockName)
    subtypes = blockData.get('subtypes', extractSubtypes(blockKey, headerData))
    if subtypes: notice('Processing %s: %s'%(blockName, subtypes))
    else: notice('Processing %s: [single block]'%(blockName))
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

    #refererence url and teaser docs
    blockSiteKey = 'doc/%s/'%docKey
    blockSiteInfo = siteInfo.get(blockSiteKey)
    if blockSiteInfo:
        title = blockSiteInfo.get('title')
        teaser = blockSiteInfo.get('teaser')
        if title: blockDesc['docs'].append('<h2>%s</h2>'%title)
        if teaser: blockDesc['docs'].append('<p>%s</p>'%teaser)
    else: warning('No site teaser found for "%s"'%blockSiteKey)
    url = 'http://liquidsdr.org/%s'%blockSiteKey
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
    header('Begin parsing and generation: %s -> %s'%(os.path.basename(resourceIn), os.path.basename(outputDest)))

    #parse the header
    contentsH = open(liquidH).read()
    contentsLines = contentsH.splitlines()
    headerData = parseHeader(contentsH)

    #parse site.json
    siteInfo = dict()
    siteJson = os.path.join(os.path.dirname(outputDest), 'site.json')
    if os.path.exists(siteJson): siteInfo = json.loads(open(siteJson).read())
    else: warning('Site info not found, doc teasers will be missing!')

    if resourceIn == "ENUMS":
        enumsTmplCpp = os.path.join(os.path.dirname(__file__), 'tmpl', 'LiquidEnums.tmpl.cpp')
        output = Template(open(enumsTmplCpp).read()).render(enums=headerData.enums)
        open(outputDest, 'w').write(output)

    else:

        #parse the blocks
        resourceName =  os.path.splitext(os.path.basename(resourceIn))[0]
        blocksData = yaml.load(open(resourceIn).read())
        if blocksData is None:
            warning('%s is empty'%resourceIn)
            blocksData = dict()

        #run the generator
        output = ""
        for blockName, blockData in blocksData.items():
            output += generateCpp(resourceName, blockName, blockData, headerData, contentsLines, siteInfo)
        open(outputDest, 'w').write(output)
        open(outputDest+'.log', 'w').write(LOG[0])
