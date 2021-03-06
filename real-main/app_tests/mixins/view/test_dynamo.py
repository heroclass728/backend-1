from uuid import uuid4

import pendulum
import pytest

from app.mixins.view.dynamo import ViewDynamo
from app.mixins.view.exceptions import ViewAlreadyExists, ViewDoesNotExist


@pytest.fixture
def view_dynamo(dynamo_client):
    yield ViewDynamo('itype', dynamo_client)


def test_add_and_increment_view(view_dynamo):
    item_id = 'iid'
    user_id = 'uid'
    view_count = 5
    viewed_at = pendulum.now('utc')
    viewed_at_str = viewed_at.to_iso8601_string()

    # verify can't increment view that doesn't exist
    with pytest.raises(ViewDoesNotExist):
        view_dynamo.increment_view_count(item_id, user_id, 1, pendulum.now('utc'))

    # verify the view does not exist
    assert view_dynamo.get_view(item_id, user_id) is None

    # add a new view, verify form is correct
    view = view_dynamo.add_view(item_id, user_id, view_count, viewed_at)
    assert view == {
        'partitionKey': 'itype/iid',
        'sortKey': 'view/uid',
        'schemaVersion': 0,
        'gsiK1PartitionKey': 'itype/iid',
        'gsiK1SortKey': f'view/{viewed_at_str}',
        'viewCount': 5,
        'firstViewedAt': viewed_at_str,
        'lastViewedAt': viewed_at_str,
    }

    # verify can't add another view with same key
    with pytest.raises(ViewAlreadyExists):
        view_dynamo.add_view(item_id, user_id, 1, pendulum.now('utc'))

    # verify a read from the DB has the form we expect
    assert view_dynamo.get_view(item_id, user_id) == view

    # increment the view, verify the new form is correct
    new_viewed_at = pendulum.now('utc')
    view = view_dynamo.increment_view_count(item_id, user_id, view_count, new_viewed_at)
    assert view == {
        'partitionKey': 'itype/iid',
        'sortKey': 'view/uid',
        'schemaVersion': 0,
        'gsiK1PartitionKey': 'itype/iid',
        'gsiK1SortKey': f'view/{viewed_at_str}',
        'viewCount': 10,
        'firstViewedAt': viewed_at_str,
        'lastViewedAt': new_viewed_at.to_iso8601_string(),
    }

    # verify a read from the DB has the form we expect
    assert view_dynamo.get_view(item_id, user_id) == view


def test_generate_views(view_dynamo):
    item_id = 'iid'

    # set up a decoy item with same partitionKey
    view_dynamo.client.add_item({'Item': {'partitionKey': 'itype/iid', 'sortKey': '-'}})

    # test generating no views
    assert list(view_dynamo.generate_views(item_id)) == []
    assert list(view_dynamo.generate_views(item_id, pks_only=True)) == []

    # add a view, test we generate it
    user_id_1 = 'uid1'
    view_dynamo.add_view(item_id, user_id_1, 1, pendulum.now('utc'))

    views = list(view_dynamo.generate_views(item_id))
    assert len(views) == 1
    assert views[0]['partitionKey'] == 'itype/iid'
    assert views[0]['sortKey'] == 'view/uid1'
    assert views[0]['viewCount'] == 1

    pks = list(view_dynamo.generate_views(item_id, pks_only=True))
    assert len(pks) == 1
    assert pks[0] == {'partitionKey': 'itype/iid', 'sortKey': 'view/uid1'}

    # add another view, test they both generate
    user_id_0 = 'uid0'
    view_dynamo.add_view(item_id, user_id_0, 2, pendulum.now('utc'))

    views = list(view_dynamo.generate_views(item_id))
    assert len(views) == 2
    assert views[0]['partitionKey'] == 'itype/iid'
    assert views[0]['sortKey'] == 'view/uid0'
    assert views[0]['viewCount'] == 2
    assert views[1]['partitionKey'] == 'itype/iid'
    assert views[1]['sortKey'] == 'view/uid1'
    assert views[1]['viewCount'] == 1

    pks = list(view_dynamo.generate_views(item_id, pks_only=True))
    assert len(pks) == 2
    assert pks[0] == {'partitionKey': 'itype/iid', 'sortKey': 'view/uid0'}
    assert pks[1] == {'partitionKey': 'itype/iid', 'sortKey': 'view/uid1'}


def test_delete_view(view_dynamo):
    # add two views, verify
    item_id1, user_id1 = [str(uuid4()), str(uuid4())]
    item_id2, user_id2 = [str(uuid4()), str(uuid4())]
    view_dynamo.add_view(item_id1, user_id1, 1, pendulum.now('utc'))
    view_dynamo.add_view(item_id2, user_id2, 2, pendulum.now('utc'))
    assert view_dynamo.get_view(item_id1, user_id1)
    assert view_dynamo.get_view(item_id2, user_id2)

    # delete one of the views, verify final state
    resp = view_dynamo.delete_view(item_id1, user_id1)
    assert resp
    assert view_dynamo.get_view(item_id1, user_id1) is None
    assert view_dynamo.get_view(item_id2, user_id2)

    # delete a view that doesn't exist, should fail softly
    resp = view_dynamo.delete_view(item_id1, user_id1)
    assert resp is None


def test_delete_views(view_dynamo):
    # test empty delete, should not error out
    view_dynamo.delete_views(x for x in ())

    # add two views
    view1 = view_dynamo.add_view('iid1', 'uid1', 1, pendulum.now('utc'))
    view2 = view_dynamo.add_view('iid2', 'uid2', 2, pendulum.now('utc'))

    # verify we see both of those in the db
    assert view_dynamo.get_view('iid1', 'uid1')
    assert view_dynamo.get_view('iid2', 'uid2')

    # delete them
    view_dynamo.delete_views(x for x in (view1, view2))

    # verify they're gone
    assert view_dynamo.get_view('iid1', 'uid1') is None
    assert view_dynamo.get_view('iid2', 'uid2') is None
