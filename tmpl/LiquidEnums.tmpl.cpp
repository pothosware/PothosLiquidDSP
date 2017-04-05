<%!
import datetime
%>

////////////////////////////////////////////////////////////////////////
// This file is machine generated ${str(datetime.datetime.today())}
////////////////////////////////////////////////////////////////////////

#include <Pothos/Config.hpp>
#include <Pothos/Exception.hpp>
#include <complex> //need complex before liquid
#include <liquid/liquid.h>
#include <string>

% for enum in enums:
static ${enum['name']} string_to_${enum['name']}(const std::string &s)
{
    % for value in enum['values']:
    if (s == "${value['name']}") return ${value['name']};
    % endfor
    throw Pothos::RuntimeException("convert string to ${enum['name']} unknown value: "+s);
}
% endfor

/***********************************************************************
 * registration
 **********************************************************************/

#include <Pothos/Plugin.hpp>

pothos_static_block(registerLiquidEnums)
{
    % for enum in enums:
    Pothos::PluginRegistry::add("/object/convert/liquid_enums/string_to_${enum['name']}", Pothos::Callable(&string_to_${enum['name']}));
    % endfor
}
