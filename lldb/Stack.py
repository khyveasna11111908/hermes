# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Stack.py contains the code used for decoding Hermes JS stack in the
lldb debugger.
Add "command script import <path_to_Stack.py>" to your ~/.lldbinit to
enable this command by default in lldb.
"""

from __future__ import absolute_import, division, print_function, unicode_literals


def _raise_eval_failure(expression, error):
    raise Exception("Fail to evaluate {}: {}".format(expression, error.GetCString()))


def __lldb_init_module(debugger, _):
    """Installs a new debugger command for dumping hermes js stack"""
    debugger.HandleCommand("command script add -f Stack.dump_js_stack jsbt")


def _evaluate_expression(frame, expression):
    """Helper function to evaluate expression in the context of input frame
    and throw error if evaluation failed. The evaluated SBValue is returned.
    """
    result_value = frame.EvaluateExpression(expression)
    if _is_eval_failed(result_value):
        _raise_eval_failure(expression, result_value.GetError())

    return result_value


def _is_eval_failed(evaluation_result):
    return evaluation_result is None or (
        evaluation_result.GetError() and evaluation_result.GetError().Fail()
    )


def _get_raw_ptr_from_shared_ptr(shared_ptr):
    """ Decode raw pointer from shared_ptr"""
    return shared_ptr.GetChildAtIndex(0)


def _get_profiler_instance_expr(frame):
    """Return the evaluation expression for getting SamplingProfiler instance"""
    expression = "::hermes::vm::SamplingProfiler::getInstance()"
    profiler_sharedptr_value = _evaluate_expression(frame, expression)

    # Currently lldb segfault while evaluating std::shared_ptr<T>::get() for GNU C++.
    # To workaround this issue we manually decode the shared_ptr raw pointer.
    profiler_raw_ptr = _get_raw_ptr_from_shared_ptr(profiler_sharedptr_value)
    return (
        "((::hermes::vm::SamplingProfiler *)%u)" % profiler_raw_ptr.GetValueAsUnsigned()
    )


def _get_hermes_runtime_expr(frame):
    """Return the evaluation expression for getting Hermes runtime"""
    return _get_profiler_instance_expr(frame) + "->threadLocalRuntime_.get()"


def _get_stdstring_summary(str_val):
    """
    Get std::string summary out of SBValue. This helper
    method is needed because lldb std::string type summary
    failed to work on GNU libraries.
    """
    str_summary = str_val.GetSummary()
    if str_summary is not None:
        return str_summary
    # Does not have summary, assume it is GNU std::string
    # and manually decode two nested levels "._M_dataplus._M_p"
    return str_val.GetChildAtIndex(0).GetChildAtIndex(0).GetSummary()


def _format_and_print_stack(stack_str_summary):
    # TODO: Verify the result is string type.
    value_str = stack_str_summary.strip('"')
    for frame in value_str.split("\\n"):
        print(frame)


def dump_js_stack(debugger, command, result, internal_dict):
    """Dump hermes js stack in string format"""
    thread = debugger.GetSelectedTarget().GetProcess().GetSelectedThread()
    leaf_frame = thread.GetFrameAtIndex(0)

    expression = _get_hermes_runtime_expr(leaf_frame) + "->getCallStackNoAlloc()"
    result_str_value = _evaluate_expression(leaf_frame, expression)

    str_summary = _get_stdstring_summary(result_str_value)
    _format_and_print_stack(str_summary)
