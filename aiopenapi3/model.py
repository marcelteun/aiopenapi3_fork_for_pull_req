from __future__ import annotations

import collections
import types
import uuid

import sys

if sys.version_info >= (3, 9):
    from typing import List, Optional, Literal, Union, Annotated
else:
    from typing import List, Optional, Union
    from typing_extensions import Annotated, Literal

from pydantic import BaseModel, Extra, Field
from pydantic.schema import field_class_to_schema

type_format_to_class = collections.defaultdict(lambda: dict())


def generate_type_format_to_class():
    """
    initialize type_format_to_class
    :return: None
    """
    global type_format_to_class
    for cls, spec in field_class_to_schema:
        if spec["type"] not in frozenset(["string", "number"]):
            continue
        type_format_to_class[spec["type"]][spec.get("format", None)] = cls


def class_from_schema(s):
    a = type_format_to_class[s.type]
    b = a.get(s.format, a[None])
    return b


class Model(BaseModel):
    class Config:
        extra: Extra.forbid

    @classmethod
    def from_schema(
        cls, shma: "SchemaBase", shmanm: List[str] = None, discriminators: List["DiscriminatorBase"] = None
    ):

        if shmanm is None:
            shmanm = []

        if discriminators is None:
            discriminators = []

        # do not create models for primitive types
        if shma.type in ("string", "integer", "number", "boolean"):
            return Model.typeof(shma)

        type_name = shma.title or getattr(shma, "_identity", None) or str(uuid.uuid4())
        namespace = dict()
        annos = dict()
        if shma.allOf:
            for i in shma.allOf:
                annos.update(Model.annotationsof(i, discriminators, shmanm))
        elif hasattr(shma, "anyOf") and shma.anyOf:
            t = tuple(
                i.get_type(names=shmanm + [i.ref], discriminators=discriminators + [shma.discriminator])
                for i in shma.anyOf
            )
            if shma.discriminator and shma.discriminator.mapping:
                annos["__root__"] = Annotated[Union[t], Field(discriminator=shma.discriminator.propertyName)]
            else:
                annos["__root__"] = Union[t]
        elif hasattr(shma, "oneOf") and shma.oneOf:
            t = tuple(
                i.get_type(names=shmanm + [i.ref], discriminators=discriminators + [shma.discriminator])
                for i in shma.oneOf
            )
            if shma.discriminator and shma.discriminator.mapping:
                annos["__root__"] = Annotated[Union[t], Field(discriminator=shma.discriminator.propertyName)]
            else:
                annos["__root__"] = Union[t]
        else:
            annos = Model.annotationsof(shma, discriminators, shmanm)
            namespace.update(Model.fieldof(shma))

        namespace["__annotations__"] = annos

        m = types.new_class(type_name, (BaseModel,), {}, lambda ns: ns.update(namespace))
        m.update_forward_refs()
        return m

    @staticmethod
    def typeof(schema: "SchemaBase"):
        r = None
        if schema.type == "integer":
            r = int
        elif schema.type == "number":
            r = class_from_schema(schema)
        elif schema.type == "string":
            r = class_from_schema(schema)
        elif schema.type == "boolean":
            r = bool
        elif schema.type == "array":
            r = List[schema.items.get_type()]
        elif schema.type == "object":
            return schema.get_type()
        elif schema.type is None:  # discriminated root
            """
            recursively define related discriminated objects
            """
            schema.get_type()
            return None
        else:
            raise TypeError(schema.type)

        return r

    @staticmethod
    def annotationsof(schema: "SchemaBase", discriminators, shmanm):
        annos = dict()
        if schema.type == "array":
            annos["__root__"] = Model.typeof(schema)
        else:

            for name, f in schema.properties.items():
                r = None
                for discriminator in discriminators:
                    if name != discriminator.propertyName:
                        continue
                    for disc, v in discriminator.mapping.items():
                        if v in shmanm:
                            r = Literal[disc]
                            break
                    else:
                        raise ValueError(schema)
                    break
                else:
                    r = Model.typeof(f)

                from . import v20, v30, v31

                if isinstance(schema, (v20.Schema, v20.Reference)):
                    if not f.required:
                        annos[name] = Optional[r]
                    else:
                        annos[name] = r
                elif isinstance(schema, (v30.Schema, v31.Schema, v30.Reference, v31.Reference)):
                    if name not in schema.required:
                        annos[name] = Optional[r]
                    else:
                        annos[name] = r
                else:
                    raise TypeError(schema)

        return annos

    @staticmethod
    def fieldof(schema: "SchemaBase"):
        r = dict()
        if schema.type == "array":
            return r
        else:
            for name, f in schema.properties.items():
                args = dict()
                for i in ["enum", "default"]:
                    v = getattr(f, i, None)
                    if v:
                        args[i] = v
                r[name] = Field(**args)
        return r


if len(type_format_to_class) == 0:
    generate_type_format_to_class()
