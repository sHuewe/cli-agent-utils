Analyze exactly one partitioned source unit and create an exhaustive, source-grounded inventory.

Source root: `{{var:source_root}}`
Unit:
{{var:unit}}

Rules:
- Treat the unit's `source_path` as the complete scope of this step. Do not inspect source files outside it.
- Base every claim on files actually inspected.
- Identify responsibilities, entry points, important components, interfaces, data/control flows, persistence/integrations, security-relevant behavior and operational behavior.
- Completeness of externally observable behavior and configuration is a hard requirement, not a sampling task.

Systematically search for externally observable functions/capabilities. Depending on the technology, inspect all relevant forms such as:
- HTTP/RPC/controllers/routes/endpoints and externally callable service façades;
- CLI commands, arguments and subcommands;
- UI/user actions represented in this source scope;
- scheduled/background jobs with externally relevant effects;
- message/event consumers, producers and handlers;
- import/export, file or protocol interfaces;
- plugin/provider/extension hooks;
- public integration APIs and other callable/observable application behavior.

Systematically search for configuration. Depending on the technology, inspect all relevant forms such as:
- configuration classes, schemas, records and property binding;
- property/YAML/JSON/XML/TOML keys and defaults;
- environment-variable lookups and mappings;
- CLI configuration flags;
- feature flags, modes and profiles;
- configurable URLs/endpoints, paths, credentials references, timeouts, retries, limits, sizes, ports and toggles;
- framework annotations or registration code that declares configurable values;
- example/default configuration shipped in the unit.

Do not omit an item because it seems small, obvious, internal-looking or rarely used when a user/operator/caller/integrator can invoke, observe or configure it.

Assign stable local IDs:
- external functions: `fn001`, `fn002`, ...
- configuration options: `cfg001`, `cfg002`, ...

For every item include concrete source evidence. Prefer path plus symbol/key where possible. If configuration is a coherent family generated from one schema, it may be one item only when the documentation will still enumerate every individual supported member.

Do not write or modify files.

Return exactly one JSON object:
{
  "unit":{
    "id":"string",
    "name":"string",
    "kind":"string",
    "source_path":"workspace-relative/path"
  },
  "summary":"string",
  "entry_points":[{"path":"string","purpose":"string"}],
  "components":[{"name":"string","responsibility":"string","evidence":["string"]}],
  "interfaces":[{"kind":"string","name":"string","evidence":["string"]}],
  "external_functions":[
    {
      "id":"fn001",
      "name":"string",
      "kind":"string",
      "description":"string",
      "evidence":["workspace-relative/path#symbol-or-location"]
    }
  ],
  "configuration_options":[
    {
      "id":"cfg001",
      "name":"string",
      "description":"string",
      "evidence":["workspace-relative/path#key-or-symbol"]
    }
  ],
  "data_flows":[{"name":"string","summary":"string","evidence":["string"]}],
  "cross_cutting_concerns":[{"name":"string","summary":"string","evidence":["string"]}],
  "candidate_topics":[{"topic":"string","why":"string","evidence":["string"]}],
  "inventory_checks":{
    "external_surface_sweep":"completed",
    "configuration_sweep":"completed"
  },
  "warnings":["string"]
}

Return valid JSON only.
