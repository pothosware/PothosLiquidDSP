<%!
import datetime
%>

////////////////////////////////////////////////////////////////////////
// This file is machine generated ${str(datetime.datetime.today())}
////////////////////////////////////////////////////////////////////////

#include <Pothos/Framework.hpp>
#include <liquid/liquid.h>

class ${blockClass} : public Pothos::Block
{
public:

    static Block *make(${constructor.paramTypesStr})
    {
        return new ${blockClass}(${constructor.paramArgsStr});
    }

    ${blockClass}(${constructor.paramTypesStr}):
        % for param in constructor.params:
        ${param.name}(${param.name}),
        % endfor
        _q(nullptr)
    {
        _q = ${constructor.name}(${constructor.paramArgsStr});

        //setup input ports
        % for input in inputs:
        ${input.name} = this->setupInput("${input.key}", typeid(${input.type}));
        % if input.alias is not None:
        ${input.name}->setAlias("${input.alias}");
        % endif
        % endfor

        //setup output ports
        % for output in outputs:
        ${output.name} = this->setupOutput("${output.key}", typeid(${output.type}));
        % if output.alias is not None:
        ${output.name}->setAlias("${output.alias}");
        % endif
        % endfor

        //register calls on this block
        % for function in initializers + setters:
        this->registerCall(this, "${function.key}", &${blockClass}::${function.key});
        % endfor
    }

    ~${blockClass}(void)
    {
        ${destructor.name}(_q);
    }

    % for function in initializers + setters:
    void ${function.key}(${function.paramTypesStr})
    {
        % for param in function.params:
        this->${param.name} = ${param.name};
        % endfor
        ${function.name}(_q, ${function.paramArgsStr});
    }
    % endfor

    void activate(void)
    {
        % for activator in activators:
        ${activator.name}(_q);
        % endfor
    }

    void work(void)
    {
        
    }

private:
    % for function in [constructor] + initializers + setters:
    % for param in function.params:
    ${param.type} ${param.name};
    % endfor
    % endfor
    ${constructor.data['rtnType']} _q;

    % for input in inputs:
    Pothos::InputPort *${input.name};
    % endfor

    % for output in outputs:
    Pothos::OutputPort *${output.name};
    % endfor
};

/***********************************************************************
 * registration
 **********************************************************************/
static Pothos::BlockRegistry register${blockClass}(
    "/liquid/${blockName}", &${blockClass}::make);

