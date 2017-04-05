<%!
import datetime
%>

////////////////////////////////////////////////////////////////////////
// This file is machine generated ${str(datetime.datetime.today())}
////////////////////////////////////////////////////////////////////////

#include <Pothos/Framework.hpp>
#include <complex> //need complex before liquid
#include <liquid/liquid.h>
#include <iostream>

${blockClasses}

/***********************************************************************
 * registration
 **********************************************************************/

% if subtypesArgs:
Pothos::Block *make_${blockClass}(${factoryArgs})
{
    % for subtype, subfactory, args in subtypesArgs:
    if (type == "${subtype}") return ${subfactory}::make(${args});
    % endfor
    throw Pothos::InvalidArgumentException("make_${blockClass}("+type+")", "Unknown type");
}
% endif

static Pothos::BlockRegistry register${blockClass}(
    "/liquid/${blockName}", &${factory});

#include <Pothos/Plugin.hpp>

pothos_static_block(register${blockClass}Docs)
{
    Pothos::PluginRegistry::add("/blocks/docs/liquid/${blockName}", std::string("${blockDescEscaped}"));
}
