// Copyright (c) 2020 Nicholas Corgan
// SPDX-License-Identifier: BSL-1.0

#include <Pothos/Plugin.hpp>

#include <Poco/Format.h>

#include <liquid/liquid.h>

#include <string>

// Simple enough JSON that we don't really need the JSON framework
static std::string getLiquidVersionInfo()
{
    return Poco::format(
               "{\"Liquid Version\": \"%s\"}",
               std::string(::liquid_libversion()));
}

// Register this so we can see the version in PothosFlow.
pothos_static_block(registerLiquidInfo)
{
    Pothos::PluginRegistry::addCall(
        "/devices/liquid/info",
        &getLiquidVersionInfo);
}
