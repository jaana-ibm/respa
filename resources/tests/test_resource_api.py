import json
import pytest
from django.core.urlresolvers import reverse
from django.contrib.gis.geos import Point

from .utils import check_only_safe_methods_allowed


@pytest.fixture
def list_url():
    return reverse('resource-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(resource_in_unit):
    return reverse('resource-detail', kwargs={'pk': resource_in_unit.pk})


def _check_permissions_dict(api_client, resource, is_admin, can_make_reservation):
    """
    Check that user permissions returned from resource endpoint contain correct values
    for given user and resource. api_client should have the user authenticated.
    """

    url = reverse('resource-detail', kwargs={'pk': resource.pk})
    response = api_client.get(url)
    assert response.status_code == 200
    permissions = response.data['user_permissions']
    assert len(permissions) == 2
    assert permissions['is_admin'] == is_admin
    assert permissions['can_make_reservations'] == can_make_reservation


@pytest.mark.django_db
def test_disallowed_methods(all_user_types_api_client, list_url, detail_url):
    """
    Tests that only safe methods are allowed to unit list and detail endpoints.
    """
    check_only_safe_methods_allowed(all_user_types_api_client, (list_url, detail_url))


@pytest.mark.django_db
def test_user_permissions_in_resource_endpoint(api_client, resource_in_unit, user):
    """
    Tests that resource endpoint returns a permissions dict with correct values.
    """
    api_client.force_authenticate(user=user)

    # normal user reservable True, expect is_admin False can_make_reservations True
    _check_permissions_dict(api_client, resource_in_unit, False, True)

    # normal user reservable False, expect is_admin False can_make_reservations False
    resource_in_unit.reservable = False
    resource_in_unit.save()
    _check_permissions_dict(api_client, resource_in_unit, False, False)

    # staff member reservable False, expect is_admin True can_make_reservations True
    user.is_staff = True
    user.save()
    api_client.force_authenticate(user=user)
    _check_permissions_dict(api_client, resource_in_unit, True, True)


@pytest.mark.django_db
def test_non_public_resource_visibility(api_client, resource_in_unit, user):
    """
    Tests that non-public resources are not returned for non-staff.
    """

    resource_in_unit.public = False
    resource_in_unit.save()

    url = reverse('resource-detail', kwargs={'pk': resource_in_unit.pk})
    response = api_client.get(url)
    assert response.status_code == 404

    # Unauthenticated
    url = reverse('resource-list')
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data['count'] == 0

    # Authenticated as non-staff
    api_client.force_authenticate(user=user)
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data['count'] == 0

    # Authenticated as staff
    user.is_staff = True
    user.save()
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data['count'] == 1

    url = reverse('resource-detail', kwargs={'pk': resource_in_unit.pk})
    response = api_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_api_resource_geo_queries(api_client, resource_in_unit):
    id_base = resource_in_unit.pk
    res = resource_in_unit

    res.location = None
    res.save()

    res.pk = id_base + "r2"
    res.location = Point(24, 60, srid=4326)
    res.save()

    res.pk = id_base + "r3"
    res.location = Point(25, 60, srid=4326)
    res.save()

    unit = resource_in_unit.unit
    unit.location = None
    unit.save()

    unit.pk = unit.pk + "u2"
    unit.location = Point(24, 61, srid=4326)
    unit.save()
    res.pk = id_base + "r4"
    res.location = None
    res.unit = unit
    res.save()

    base_url = reverse('resource-list')

    response = api_client.get(base_url)
    assert response.data['count'] == 4
    results = response.data['results']
    assert 'distance' not in results[0]

    url = base_url + '?lat=60&lon=24'
    response = api_client.get(url)
    assert response.data['count'] == 4
    results = response.data['results']
    assert results[0]['id'].endswith('r2')
    assert results[0]['distance'] == 0
    assert results[1]['id'].endswith('r3')
    assert results[1]['distance'] == 55597
    assert results[2]['distance'] == 111195
    assert 'distance' not in results[3]

    # Check that location is inherited from the resource's unit
    url = base_url + '?lat=61&lon=25&distance=100000'
    response = api_client.get(url)
    assert response.data['count'] == 1
    results = response.data['results']
    assert results[0]['id'].endswith('r4')
    assert results[0]['distance'] == 53907