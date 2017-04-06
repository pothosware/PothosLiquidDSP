class ${blockClass} : public Pothos::Block
{
public:

    static Block *make(${constructor.paramTypesStr})
    {
        return new ${blockClass}(${constructor.passArgsStr});
    }

    ${blockClass}(${constructor.paramTypesStr}):
        % for param in constructor.params:
        % if param in constructor.externalParams:
        ${param.name}(${param.name}),
        % else:
        ${param.name}(${param.default}),
        % endif
        % endfor
        % for function in initializers + setters:
        % for param in function.params:
        % if param not in constructor.params and param.default is not None:
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
        % for function in initializers + setters + getters:
        this->registerCall(this, "${function.key}", &${blockClass}::${function.key});
        % endfor

        //register probes on this block
        % for function in getters:
        this->registerProbe("${function.key}", "probe_${function.key}", "${function.key}_triggered");
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

    % for function in getters:
    ${function.rtnType} ${function.key}(void)
    {
        return ${function.name}(_q);
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
        const unsigned int numAvailableIn = this->workInfo().minAllInElements;
        const unsigned int numAvailableOut = this->workInfo().minAllOutElements;
        unsigned int numRead(0);
        unsigned int numWritten(0);

        //perform work on buffers
        % if worker.mode == 'STANDARD_LOOP':
        unsigned int N = std::min(numAvailableIn/${worker.decim}, numAvailableOut/${worker.interp});
        if (N == 0) return;
        for (unsigned int i = 0; i < N; i++)
        {
            % for function in worker.functions:
            ${function.name}(_q, ${function.args});
            % endfor
            % for factor, ports in [(worker.decim, inputs), (worker.interp, outputs)]:
            % for port in ports:
            ${port.buffVar} += ${factor};
            % endfor
            % endfor
        }
        numRead = N*${worker.decim};
        numWritten = N*${worker.interp};

        % elif worker.mode == 'VARIABLE_OUTPUT_BLOCK':
        unsigned int N = std::min(numAvailableIn, static_cast<unsigned int>(numAvailableOut/${worker.factor}));
        if (N == 0) return;
        % for function in worker.functions:
        ${function.name}(_q, ${function.args});
        % endfor
        numRead = N;

        % elif worker.mode == 'STANDARD_BLOCK':
        unsigned int N = std::min(numAvailableIn/${worker.decim}, numAvailableOut/${worker.interp});
        if (N == 0) return;
        % for function in worker.functions:
        ${function.name}(_q, ${function.args});
        % endfor
        numRead = N*${worker.decim};
        numWritten = N*${worker.interp};
        % endif

        //produce and consume resources
        % for port in inputs:
        ${port.portVar}->consume(numRead);
        % endfor
        % for port in outputs:
        ${port.portVar}->produce(numWritten);
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
    % for param in constructor.params:
    ${param.type} ${param.name};
    % endfor
    % for function in initializers + setters:
    % for param in function.params:
    % if param not in constructor.params:
    ${param.type} ${param.name};
    % endif
    % endfor
    % endfor
    ${constructor.rtnType} _q;

    % for input in inputs:
    Pothos::InputPort *${input.portVar};
    % endfor
    % for output in outputs:
    Pothos::OutputPort *${output.portVar};
    % endfor
};
