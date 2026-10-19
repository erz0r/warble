"""mcp server (stdio) and json-lines `serve` mode, both generated from the cli's command table.

every cli command becomes a tool with the same parameters. a tool call is turned back into an argv
and run through the very same argparse parser and command function, so the cli and the server
cannot drift apart. models stay loaded between calls. inspect / analyze / compare return their
images as image content (the most useful ones first, `max_images` to change how many).
"""

import base64
import contextlib
import io
import json
import os
import sys

from .cli import COMMANDS, build_parser
from .errors import WarbleError

IMAGE_ORDER = ("pianoroll", "cents_error", "spec_linear", "compare_pitch", "compare_ab", "ref_pitch", "joins", "vibrato", "spec_mel", "lanes")
DEFAULT_MAX_IMAGES = 6


def _arg_name(flags, kwargs):
    if "dest" in kwargs:
        return kwargs["dest"]
    longs = [f for f in flags if f.startswith("--")]
    f = longs[0] if longs else flags[0]
    return f.lstrip("-").replace("-", "_")


def schema_for(spec):
    props, required = {}, []
    for flags, kw in spec["args"]:
        name = _arg_name(flags, kw)
        positional = not flags[0].startswith("-")
        p = {"description": kw.get("help", "")}
        action = kw.get("action")
        if action == "store_true":
            p["type"] = "boolean"
        elif action == "append" or kw.get("nargs") in ("*", "+"):
            p["type"] = "array"
            p["items"] = {"type": "string"}
        elif kw.get("type") is int:
            p["type"] = "integer"
        elif kw.get("type") is float:
            p["type"] = "number"
        else:
            p["type"] = "string"
        if kw.get("choices"):
            p["enum"] = list(kw["choices"])
        if kw.get("default") not in (None, argparse_suppress()) and action != "store_true":
            p["default"] = kw["default"]
        props[name] = p
        if (positional and kw.get("nargs") not in ("?", "*")) or kw.get("required"):
            required.append(name)
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def argparse_suppress():
    import argparse

    return argparse.SUPPRESS


def to_argv(command, arguments):
    """tool arguments -> argv for the cli parser."""
    spec = COMMANDS[command]
    argv = [command]
    arguments = dict(arguments or {})
    known = {_arg_name(f, k) for f, k in spec["args"]}
    unknown = set(arguments) - known - {"max_images"}
    if unknown:
        raise WarbleError("bad_arguments", f"{command}: unknown arguments {sorted(unknown)}", hint=f"arguments: {sorted(known)}")
    for flags, kw in spec["args"]:
        name = _arg_name(flags, kw)
        if name not in arguments or arguments[name] is None:
            continue
        v = arguments[name]
        positional = not flags[0].startswith("-")
        flag = next((f for f in flags if f.startswith("--")), flags[0])
        if kw.get("action") == "store_true":
            if v:
                argv.append(flag)
        elif kw.get("action") == "append":
            for item in v if isinstance(v, list) else [v]:
                argv.append(f"{flag}={item}")
        elif positional:
            argv.extend([str(x) for x in v] if isinstance(v, list) else [str(v)])
        elif isinstance(v, list):
            argv.append(flag)
            argv.extend(str(x) for x in v)
        else:
            argv.append(f"{flag}={v}")
    return argv


def run(command, arguments):
    """run one command exactly as the cli would. returns the result dict (or an error dict)."""
    if command not in COMMANDS:
        return {"error": "unknown_command", "message": f"no command '{command}'", "hint": f"commands: {sorted(COMMANDS)}"}
    parser = build_parser()
    try:
        a = parser.parse_args(to_argv(command, arguments))
        # logs go to stderr already; anything printed to stdout by libraries must not corrupt the protocol
        with contextlib.redirect_stdout(sys.stderr):
            return COMMANDS[command]["fn"](a)
    except WarbleError as e:
        return e.to_json()
    except Exception as e:  # noqa: BLE001
        import traceback

        return {"error": "internal_error", "message": f"{type(e).__name__}: {e}", "details": {"traceback": traceback.format_exc().splitlines()[-8:]}}


def _images(result, max_images):
    paths = []
    imgs = result.get("images") if isinstance(result, dict) else None
    if not imgs:
        return []
    ranked = sorted(imgs, key=lambda p: next((i for i, k in enumerate(IMAGE_ORDER) if k in os.path.basename(p)), len(IMAGE_ORDER)))
    for p in ranked[:max_images]:
        if os.path.isfile(p):
            paths.append(p)
    return paths


def _json_default(o):
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
    except ImportError:
        pass
    return str(o)


def serve_mcp():
    import anyio

    try:
        import mcp.types as types
        from mcp.server.lowlevel import Server
        from mcp.server.stdio import stdio_server
    except ImportError:
        raise WarbleError("mcp_missing", "the mcp server needs the mcp package", hint="pip install mcp")

    tools = []
    for name, spec in COMMANDS.items():
        if name in ("mcp", "serve"):
            continue
        schema = schema_for(spec)
        if name in ("inspect", "analyze", "compare"):
            schema["properties"]["max_images"] = {"type": "integer", "default": DEFAULT_MAX_IMAGES, "description": "how many images to return inline"}
        tools.append(types.Tool(name=name, description=spec["help"], inputSchema=schema))

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=tools)

    async def call_tool(ctx, params):
        args = dict(params.arguments or {})
        max_images = int(args.pop("max_images", DEFAULT_MAX_IMAGES))
        result = await anyio.to_thread.run_sync(run, params.name, args)
        text = json.dumps(result, ensure_ascii=False, default=_json_default)
        content = [types.TextContent(type="text", text=text)]
        for p in _images(result, max_images):
            with open(p, "rb") as f:
                content.append(types.ImageContent(type="image", data=base64.b64encode(f.read()).decode(), mimeType="image/png"))
        is_error = isinstance(result, dict) and "error" in result and isinstance(result.get("error"), str)
        structured = json.loads(text) if isinstance(result, dict) else {"result": json.loads(text)}
        return types.CallToolResult(content=content, structuredContent=structured, isError=is_error)

    server = Server("warble", on_list_tools=list_tools, on_call_tool=call_tool)

    async def main():
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    anyio.run(main)


def serve_lines(inp=None, out=None):
    """json lines on stdin: {"id": any, "command": "sing", "args": {...}} -> one json line per request."""
    inp = inp or sys.stdin
    out = out or sys.stdout
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            out.write(json.dumps({"error": "bad_request", "message": str(e)}) + "\n")
            out.flush()
            continue
        if req.get("command") in ("quit", "exit"):
            break
        res = run(req.get("command"), req.get("args") or {})
        out.write(json.dumps({"id": req.get("id"), "result": res}, ensure_ascii=False, default=_json_default) + "\n")
        out.flush()
