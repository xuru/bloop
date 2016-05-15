import enum
import bloop.condition
import bloop.util


class ModifyMode(enum.Enum):
    """
    Tracking mode for a modification against a given column's name.
    Almost all updates are `overwrite`.  The most common use of
    insert_on_missing is for intermediate paths in documents, or for other
    containers where partial updates are possible.
    """
    overwrite = 0
    insert_on_missing = 1


_tracking = bloop.util.WeakDefaultDictionary(
    lambda: {"changes": dict(), "snapshot": None, "synced": False})


def clear(obj):
    """Store a snapshot of an entirely empty object.

    Usually called after deleting an object.
    """
    _tracking[obj]["synced"] = True
    snapshot = bloop.condition.Condition()
    for column in sorted(obj.Meta.columns, key=lambda col: col.dynamo_name):
        snapshot &= column.is_(None)
    _tracking[obj]["snapshot"] = snapshot


def mark(obj, column):
    """
    Mark a column for a given object as being modified in any way.
    Any marked columns will be pushed (possibly as DELETES) in
    future UpdateItem calls that include the object.
    """
    _tracking[obj]["changes"][column.model_name] = (ModifyMode.overwrite, None)


def sync(obj, engine):
    """Mark the object as having been persisted at least once.

    Store the latest snapshot of all marked values."""
    _tracking[obj]["synced"] = True
    snapshot = bloop.condition.Condition()
    # Local cache for faster lookup
    column_index = obj.Meta.columns_by_model_name
    for model_name in sorted(_tracking[obj]["changes"].keys()):
        column = column_index[model_name]
        value = getattr(obj, model_name, None)
        # Don't try to dump Nones through the typedef
        if value is not None:
            value = engine._dump(column.typedef, value)
        condition = column == value
        # The renderer shouldn't try to dump the value again.
        # We're dumping immediately in case the value is mutable,
        # such as a set or (many) custom data types.
        condition.dumped = True
        snapshot &= condition
    _tracking[obj]["snapshot"] = snapshot


def get_snapshot(obj):
    # Cached value
    condition = _tracking[obj]["snapshot"]
    if condition is not None:
        return condition

    # If the object has never been synced, create and cache
    # a condition that expects every column to be empty
    clear(obj)
    return _tracking[obj]["snapshot"]


def get_update(obj):
    """Creates a dict of changes to make for a given object.

    Returns:
        dict: A dict with two keys "SET" and "REMOVE".

        The dict has the following format::

            {
                "SET": [(Column<Foo>, obj.Foo), (Column<Bar>, obj.Bar), ...],
                "REMOVE": [Column<Baz>, ...]
            }

    """
    diff = {"SET": [], "REMOVE": []}
    key = set((obj.Meta.hash_key, obj.Meta.range_key))
    for model_name in _tracking[obj]["changes"]:
        column = obj.Meta.columns_by_model_name[model_name]
        if column in key:
            continue
        value = getattr(obj, column.model_name, None)
        if value is not None:
            diff["SET"].append((column, value))
        # None (or missing, an implicit None) expects the
        # value to be empty (missing) in Dynamo.
        else:
            diff["REMOVE"].append(column)
    return diff
