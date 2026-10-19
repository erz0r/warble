"""read an onnx model's input and output signatures without building a session."""

import os

import onnx

_DTYPES = {
    onnx.TensorProto.FLOAT: "float32",
    onnx.TensorProto.FLOAT16: "float16",
    onnx.TensorProto.DOUBLE: "float64",
    onnx.TensorProto.INT64: "int64",
    onnx.TensorProto.INT32: "int32",
    onnx.TensorProto.BOOL: "bool",
    onnx.TensorProto.UINT8: "uint8",
    onnx.TensorProto.INT8: "int8",
}


def _value_info(vi):
    t = vi.type.tensor_type
    shape = []
    for d in t.shape.dim:
        if d.HasField("dim_value"):
            shape.append(d.dim_value)
        elif d.HasField("dim_param"):
            shape.append(d.dim_param)
        else:
            shape.append("?")
    return {"name": vi.name, "dtype": _DTYPES.get(t.elem_type, f"type{t.elem_type}"), "shape": shape}


def describe(path):
    """return {inputs, outputs, opset, size_mb} for an onnx file, or {error} if it can't be read."""
    try:
        model = onnx.load(path, load_external_data=False)
    except Exception as e:  # noqa: BLE001 - any parse failure is reported, not raised
        return {"error": f"cannot read onnx: {e}"}
    inits = {i.name for i in model.graph.initializer}
    inputs = [_value_info(i) for i in model.graph.input if i.name not in inits]
    outputs = [_value_info(o) for o in model.graph.output]
    opsets = {o.domain or "ai.onnx": o.version for o in model.opset_import}
    return {
        "inputs": inputs,
        "outputs": outputs,
        "opset": opsets,
        "size_mb": round(os.path.getsize(path) / 1e6, 2),
    }


def input_names(path):
    info = describe(path)
    return [i["name"] for i in info.get("inputs", [])]
