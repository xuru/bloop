import base64
from typing import Type
from marshmallow import Schema, decorators, fields

from .. import BaseModel, signals, types


class Base64Field(fields.Field):
    def _serialize(self, value, attr, obj):
        if value is None:
            return None
        assert isinstance(value, bytes)
        return base64.b64encode(value).decode("utf-8")

    def _deserialize(self, value, attr, data):
        if value is None:
            return None
        assert isinstance(value, str)
        return base64.b64decode(value.encode("utf-8"))


class SetField(fields.List):
    def _deserialize(self, value, attr, data):
        value = super()._deserialize(value, attr, data)
        if value is None:
            return value
        return set(value)


schema_generation_hook = None
simple_fields = {
    types.Binary: Base64Field,
    types.Boolean: fields.Boolean,
    types.DateTime: fields.DateTime,
    types.Integer: fields.Integer,
    types.Number: fields.Number,
    types.String: fields.String,
    types.UUID: fields.UUID
}
collection_fields = {
    types.Set: SetField,
    types.List: fields.List,
}
nested_fields = {
    types.Map: fields.Nested
}


def register_type(bloop_type: Type[types.Type], field_type: Type[fields.Field], mapping: str="simple") -> None:
    {
        "simple": simple_fields,
        "collection": collection_fields,
        "nested": nested_fields
    }[mapping][bloop_type] = field_type


def field_for_type(bloop_type, **field_kwargs) -> fields.Field:
    assert isinstance(bloop_type, types.Type)
    cls = bloop_type.__class__
    if cls in simple_fields:
        return simple_fields[cls](**field_kwargs)
    elif cls in collection_fields:
        inner_cls = field_for_type(bloop_type.inner_typedef, **field_kwargs)
        return collection_fields[cls](inner_cls, **field_kwargs)
    elif cls in nested_fields:
        schema = type(
            "_" + cls.__name__ + "Schema",
            (Schema, ),
            {
                name: field_for_type(inner_type)
                for (name, inner_type) in bloop_type.types.items()
            }
        )
        return nested_fields[cls](schema, **field_kwargs)
    else:
        raise ValueError("Unknown bloop type {}".format(type(bloop_type)))


def create_schema(model: Type[BaseModel], **field_kwargs) -> Type[Schema]:
    attrs = {
        column.model_name: field_for_type(column.typedef, **field_kwargs)
        for column in model.Meta.columns
    }
    attrs["__generated_bloop_post_load"] = decorators.post_load(
        lambda self, data: model.Meta.init(**data)
    )
    return type(model.__name__ + "Schema", (Schema,), attrs)


def install_schema_generation_hook(**field_kwargs):
    global schema_generation_hook
    if not schema_generation_hook:
        @signals.model_created.connect
        def schema_generation_hook(_, *, model: Type[BaseModel], **__) -> None:
            model.Meta.schema_cls = create_schema(model, **field_kwargs)
