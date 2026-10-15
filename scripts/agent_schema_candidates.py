"""Offline-only schema isolation; no client, storage, keys or network execution."""

import copy
import json
from types import SimpleNamespace

from google.genai import _api_client, _common, models as sdk_models, types

from backend.agent.schemas import diagnosis_response_json_schema


FIELD_GROUPS = {
    "E1": ("inspection_id", "overall_summary", "limitations"),
    "E2": ("observed_facts", "possible_causes", "recommended_checks"),
}
REVIEWED_KEYS = frozenset({
    "$defs", "$ref", "type", "title", "description", "enum", "items", "minItems", "maxItems",
    "minimum", "maximum", "anyOf", "properties", "additionalProperties", "required",
})


def c_schema():
    return {"type": "object", "properties": {
        "summary": {"type": "string"}, "observed_facts": {"type": "array", "items": {
            "type": "object", "properties": {
                "evidence_id": {"type": "string"}, "source_field": {"type": "string"},
                "observed_value": {"type": "string"},
            }, "required": ["evidence_id", "source_field", "observed_value"],
        }},
    }, "required": ["summary", "observed_facts"]}


def serialized_request(schema):
    config = types.GenerateContentConfig(
        system_instruction="Use only the synthetic fixture and return JSON matching the supplied schema. No tools are available.",
        temperature=0, candidate_count=1, max_output_tokens=4096,
        response_mime_type="application/json", response_json_schema=copy.deepcopy(schema),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True), automatic_continuation=False,
        http_options=types.HttpOptions(api_version="v1beta", timeout=15000,
            retry_options=types.HttpRetryOptions(attempts=1)),
    )
    parameters = types._GenerateContentParameters(model="gemini-3.8-flash", config=config,
        contents=[types.Content(role="user", parts=[types.Part.from_text(
            text="Synthetic fixture: a generic test record is available. Provide one short summary.",
        )])])
    converted = sdk_models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), parameters)
    body = _common.encode_unserializable_types(_common.convert_to_dict(converted))
    builder = SimpleNamespace(vertexai=False, project=None, location=None, api_key=None, custom_base_url=None,
        _http_options=types.HttpOptions(api_version="v1beta", base_url="https://generativelanguage.googleapis.com/", headers={}))
    return _api_client.BaseApiClient._build_request(builder, "post", "models/gemini-3.8-flash:generateContent",
        body, config.http_options).data


def schema_nodes(schema, path=""):
    yield path, schema
    for name in ("properties", "$defs"):
        for key, child in schema.get(name, {}).items():
            yield from schema_nodes(child, f"{path}/{name}/{key}")
    if "items" in schema:
        yield from schema_nodes(schema["items"], path + "/items")
    for index, child in enumerate(schema.get("anyOf", [])):
        yield from schema_nodes(child, f"{path}/anyOf/{index}")


def _definition(schema, reference):
    if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
        raise ValueError("INVALID_LOCAL_REFERENCE")
    name = reference[len("#/$defs/"):]
    if name not in schema.get("$defs", {}):
        raise ValueError("UNRESOLVED_REFERENCE")
    return name, schema["$defs"][name]


def audit_schema(schema):
    nodes = list(schema_nodes(schema))
    for path, node in nodes:
        if set(node) - REVIEWED_KEYS:
            raise ValueError("UNREVIEWED_SCHEMA_KEY")
        if "type" in node and node["type"] not in {"object", "array", "string", "boolean", "integer", "number", "null"}:
            raise ValueError("INVALID_SCHEMA_TYPE")
        if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
            raise ValueError("INVALID_ENUM")
        if "required" in node:
            required = node["required"]
            if not isinstance(required, list) or len(required) != len(set(required)) or not set(required) <= set(node.get("properties", {})):
                raise ValueError("INVALID_REQUIRED_FIELDS")
        if "$ref" in node:
            _definition(schema, node["$ref"])
            if set(node) != {"$ref"}:
                raise ValueError("REFERENCE_SIBLINGS")
        if "anyOf" in node and not node["anyOf"]:
            raise ValueError("EMPTY_UNION")
        if node.get("type") == "array" and "items" not in node:
            raise ValueError("MISSING_ARRAY_ITEMS")
        for name in ("minItems", "maxItems"):
            if name in node and (type(node[name]) is not int or node[name] < 0):
                raise ValueError("INVALID_ARRAY_BOUND")
        if node.get("minItems", 0) > node.get("maxItems", float("inf")):
            raise ValueError("INCONSISTENT_ARRAY_BOUNDS")

    def depth(node, active=()):
        if "$ref" in node:
            name, target = _definition(schema, node["$ref"])
            if name in active:
                raise ValueError("CYCLIC_REFERENCE")
            return depth(target, (*active, name))
        children = list(node.get("properties", {}).values())
        children += [node["items"]] if "items" in node else []
        children += node.get("anyOf", [])
        return int(node.get("type") in {"object", "array"}) + max([depth(child, active) for child in children] or [0])

    container_depth = depth(schema)
    for definition in schema.get("$defs", {}).values():
        depth(definition)
    keywords = sorted(set().union(*(set(node) for path, node in nodes)))
    return {
        "schema_bytes": len(json.dumps(schema, ensure_ascii=False).encode("utf-8")),
        "container_depth": container_depth, "nodes": len(nodes), "keywords": keywords,
        "definitions": len(schema.get("$defs", {})),
        "refs": sum("$ref" in node for path, node in nodes),
        "unions": sum("anyOf" in node for path, node in nodes),
        "enums": sum("enum" in node for path, node in nodes),
        "null_types": sum(node.get("type") == "null" for path, node in nodes),
        "arrays": sum(node.get("type") == "array" for path, node in nodes),
        "closed_objects": sum(node.get("additionalProperties") is False for path, node in nodes),
        "required": list(schema.get("required", [])), "server_acceptance": "NOT TESTED",
    }


def _attach_definitions(candidate, source):
    needed = [node["$ref"] for path, node in schema_nodes(candidate) if "$ref" in node]
    definitions = {}
    while needed:
        reference = needed.pop()
        name, definition = _definition(source, reference)
        if name not in definitions:
            definitions[name] = copy.deepcopy(definition)
            needed.extend(node["$ref"] for path, node in schema_nodes(definition) if "$ref" in node)
    if definitions:
        candidate["$defs"] = definitions


def build_candidates(c_source=None, d_source=None):
    base = copy.deepcopy(c_source if c_source is not None else c_schema())
    full = copy.deepcopy(d_source if d_source is not None else diagnosis_response_json_schema())
    base = serialized_request(base)["generationConfig"]["responseJsonSchema"]
    full = serialized_request(full)["generationConfig"]["responseJsonSchema"]
    if set(FIELD_GROUPS["E1"]) & set(FIELD_GROUPS["E2"]) or set().union(*map(set, FIELD_GROUPS.values())) != set(full["properties"]):
        raise ValueError("FIELD_PARTITION_MISMATCH")
    candidates = {}
    for name, fields in FIELD_GROUPS.items():
        candidate = copy.deepcopy(base)
        for field in fields:
            candidate["properties"][field] = copy.deepcopy(full["properties"][field])
            if field in full["required"] and field not in candidate["required"]:
                candidate["required"].append(field)
        _attach_definitions(candidate, full)
        candidates[name] = candidate

    enum_union = copy.deepcopy(base)
    enum_union["properties"]["overall_summary"] = copy.deepcopy(full["properties"]["overall_summary"])
    enum_union["required"].append("overall_summary")
    fact = enum_union["properties"]["observed_facts"]["items"]
    full_fact = full["$defs"]["ObservedFact"]
    for field in ("source_tool", "source_event", "observed_value"):
        fact["properties"][field] = copy.deepcopy(full_fact["properties"][field])
        if field in full_fact["required"] and field not in fact["required"]:
            fact["required"].append(field)
    candidates["E3"] = enum_union

    arrays = copy.deepcopy(base)
    for name in ("minItems", "maxItems"):
        arrays["properties"]["observed_facts"][name] = full["properties"]["observed_facts"][name]
    candidates["E4"] = arrays

    references = copy.deepcopy(base)
    references["$defs"] = {"ObservedFact": references["properties"]["observed_facts"]["items"]}
    references["properties"]["observed_facts"]["items"] = {"$ref": "#/$defs/ObservedFact"}
    candidates["E5"] = references

    closed = copy.deepcopy(base)
    closed["additionalProperties"] = False
    closed["properties"]["observed_facts"]["items"]["additionalProperties"] = False
    candidates["E6"] = closed
    for candidate in candidates.values():
        audit_schema(candidate)
    return candidates


def build_e2_subcandidate(fields, source=None):
    original = copy.deepcopy(source if source is not None else build_candidates()["E2"])
    selected = tuple(fields)
    allowed = set(FIELD_GROUPS["E2"])
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= allowed:
        raise ValueError("INVALID_E2_FIELD_SELECTION")
    audit_schema(original)
    if set(original["properties"]) != {"summary", *allowed}:
        raise ValueError("E2_SOURCE_MISMATCH")
    candidate = {name: copy.deepcopy(value) for name, value in original.items()
                 if name not in {"properties", "required", "$defs"}}
    candidate["properties"] = {"summary": copy.deepcopy(original["properties"]["summary"])}
    candidate["required"] = ["summary"]
    if "observed_facts" not in selected:
        facts = copy.deepcopy(original["properties"]["observed_facts"])
        facts["items"] = {"type": "object", "properties": {
            "fact_id": copy.deepcopy(original["$defs"]["ObservedFact"]["properties"]["fact_id"]),
        }, "required": ["fact_id"]}
        candidate["properties"]["observed_facts"] = facts
        candidate["required"].append("observed_facts")
    for name in selected:
        candidate["properties"][name] = copy.deepcopy(original["properties"][name])
        if name in original["required"]:
            candidate["required"].append(name)
    _attach_definitions(candidate, original)
    audit_schema(candidate)
    return candidate


def build_e2_partitions(source=None):
    original = copy.deepcopy(source if source is not None else build_candidates()["E2"])
    return {
        "E2-A": build_e2_subcandidate(("observed_facts",), original),
        "E2-B": build_e2_subcandidate(("possible_causes", "recommended_checks"), original),
    }


def candidate_report():
    schemas = {"C": c_schema(), "D": diagnosis_response_json_schema(), **build_candidates(), **build_e2_partitions()}
    return {name: audit_schema(serialized_request(schema)["generationConfig"]["responseJsonSchema"])
            for name, schema in schemas.items()}


if __name__ == "__main__":
    print(json.dumps(candidate_report(), ensure_ascii=False, indent=2))
