type SchemaShape = Record<string, unknown> & { __optional?: boolean };

function markOptional(schema: SchemaShape): SchemaShape {
  return { ...schema, __optional: true };
}

function unmark(schema: SchemaShape): Record<string, unknown> {
  const { __optional: _optional, ...rest } = schema;
  return rest;
}

export const Type = {
  String(options: Record<string, unknown> = {}): SchemaShape {
    return { type: "string", ...options };
  },
  Number(options: Record<string, unknown> = {}): SchemaShape {
    return { type: "number", ...options };
  },
  Boolean(options: Record<string, unknown> = {}): SchemaShape {
    return { type: "boolean", ...options };
  },
  Unknown(): SchemaShape {
    return {};
  },
  Literal(value: string | number | boolean, options: Record<string, unknown> = {}): SchemaShape {
    return { const: value, ...options };
  },
  Array(items: SchemaShape, options: Record<string, unknown> = {}): SchemaShape {
    return { type: "array", items: unmark(items), ...options };
  },
  Optional(schema: SchemaShape): SchemaShape {
    return markOptional(schema);
  },
  Union(schemas: SchemaShape[], options: Record<string, unknown> = {}): SchemaShape {
    return { anyOf: schemas.map(unmark), ...options };
  },
  Record(keySchema: SchemaShape, valueSchema: SchemaShape, options: Record<string, unknown> = {}): SchemaShape {
    const keyType = keySchema.type;
    if (keyType !== "string") {
      throw new Error("Only string-keyed records are supported.");
    }
    return { type: "object", additionalProperties: unmark(valueSchema), ...options };
  },
  Object(properties: Record<string, SchemaShape>, options: Record<string, unknown> = {}): SchemaShape {
    const normalized: Record<string, unknown> = {};
    const required: string[] = [];
    for (const [name, schema] of Object.entries(properties)) {
      normalized[name] = unmark(schema);
      if (!schema.__optional) {
        required.push(name);
      }
    }
    const payload: SchemaShape = {
      type: "object",
      properties: normalized,
      ...options,
    };
    if (required.length) {
      payload.required = required;
    }
    return payload;
  },
};
