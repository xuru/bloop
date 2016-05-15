import uuid
from bloop import tracking


def test_init_marks(User):
    user = User(id=uuid.uuid4(), unused="unknown kwarg")
    expected = {"id": (tracking.ModifyMode.overwrite, None)}
    actual = tracking._tracking[user]["changes"]
    assert actual == expected


def test_delete_unknown(User):
    """ Even if a field that doesn't exist is deleted, it's marked """
    user = User(id=uuid.uuid4())
    try:
        del user.email
    except AttributeError:
        # Expected - regardless of the failure to lookup, the remote
        # should expect a delete
        pass
    assert "email" in tracking._tracking[user]["changes"]

    diff = tracking.get_update(user)
    assert diff["REMOVE"] == [User.email]


def test_get_update(User):
    """ hash_key shouldn't be in the dumped SET dict """
    user = User(id=uuid.uuid4(), email="support@domain.com")
    diff = tracking.get_update(user)

    assert not diff["REMOVE"]
    assert diff["SET"] == [(User.email, "support@domain.com")]


def test_tracking_empty_update(ComplexModel):
    """ no SET changes for hash and range key only """
    model = ComplexModel(name=(uuid.uuid4()), date="now")
    expected = set(["name", "date"])
    actual = set(tracking._tracking[model]["changes"])
    assert actual == expected

    # Dynamo doesn't send the Key (hash/range) as part of the UPDATE expr
    update = tracking.get_update(model)
    assert update == {"SET": [], "REMOVE": []}
