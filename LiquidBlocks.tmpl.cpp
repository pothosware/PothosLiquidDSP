<%!
import datetime
%>

////////////////////////////////////////////////////////////////////////
// This file is machine generated ${str(datetime.datetime.today())}
////////////////////////////////////////////////////////////////////////

#include <Pothos/Framework.hpp>
#include <liquid/liquid.h>
#include <complex>
#include <iostream>

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
        % for function in initializers + setters:
        % for param in function.params:
        % if param.default is not None:
        ${param.name}(${param.default}),
        % endif
        % endfor
        % endfor
        _q(nullptr)
    {
        _q = ${constructor.name}(${constructor.paramArgsStr});

        //setup ports
        % for setupFcn, ports in [('setupInput', inputs), ('setupOutput', outputs)]:
        % for port in ports:
        ${port.portVar} = this->${setupFcn}("${port.key}", typeid(${port.portType}));
        % if port.alias is not None:
        ${port.portVar}->setAlias("${port.alias}");
        % endif
        % if port.reserve is not None:
        ${port.portVar}->setReserve(${port.reserve});
        % endif
        % endfor
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
        % for param in function.externalParams:
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
        //get pointers to port buffers
        % for port in inputs + outputs:
        auto ${port.buffVar} = ${port.portVar}->buffer().as<${port.type} *>();
        % endfor

        //calculate available input
        const size_t numIn = this->workInfo().minAllInElements;
        const size_t numOut = this->workInfo().minAllOutElements;
        size_t N = std::min(numIn/${worker.decim}, numOut/${worker.interp});
        if (N == 0) return;

        //perform work on buffers
        % if worker.loop:
        for (size_t i = 0; i < N; i++)
        {
            ${worker.fcnName}(_q, ${worker.funcArgs});
            % for factor, ports in [(worker.decim, inputs), (worker.interp, outputs)]:
            % for port in ports:
            ${port.buffVar} += ${factor};
            % endfor
            % endfor
        }
        % else:
        ${worker.fcnName}(_q, ${worker.funcArgs});
        % endif

        //produce and consume resources
        % for method, factor, ports in [('consume', worker.decim, inputs), ('produce', worker.interp, outputs)]:
        % for port in ports:
        ${port.portVar}->${method}(N*${factor});
        % endfor
        % endfor
    }

    void propagateLabels(const Pothos::InputPort *input)
    {
        for (const auto &label : input->labels())
        {
            % for output in outputs:
            ${output.portVar}->postLabel(label.toAdjusted(${worker.interp}, ${worker.decim}));
            % endfor
        }
    }

private:
    % for function in [constructor] + initializers + setters:
    % for param in function.params:
    ${param.type} ${param.name};
    % endfor
    % endfor
    ${constructor.data['rtnType']} _q;

    % for input in inputs:
    Pothos::InputPort *${input.portVar};
    % endfor
    % for output in outputs:
    Pothos::OutputPort *${output.portVar};
    % endfor
};

/***********************************************************************
 * registration
 **********************************************************************/
static Pothos::BlockRegistry register${blockClass}(
    "/liquid/${blockName}", &${blockClass}::make);

#include <Pothos/Plugin.hpp>

pothos_static_block(register${blockClass}Docs)
{
    Pothos::PluginRegistry::add("/blocks/docs/liquid/${blockName}", std::string("${blockDescEscaped}"));
}
