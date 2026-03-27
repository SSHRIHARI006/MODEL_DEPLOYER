import pytest

from deployments.models import Deployment

pytestmark = pytest.mark.django_db


def test_state_machine_valid_transitions(model_version):
    dep = Deployment.objects.create(model_version=model_version)

    dep.transition_to(Deployment.Status.BUILDING)
    dep.save(update_fields=["status"])
    assert dep.status == Deployment.Status.BUILDING

    dep.transition_to(Deployment.Status.RUNNING)
    dep.save(update_fields=["status"])
    assert dep.status == Deployment.Status.RUNNING

    dep.transition_to(Deployment.Status.STOPPED)
    dep.save(update_fields=["status"])
    assert dep.status == Deployment.Status.STOPPED


def test_state_machine_rejects_invalid_transition(model_version):
    dep = Deployment.objects.create(model_version=model_version)

    with pytest.raises(ValueError):
        dep.transition_to(Deployment.Status.RUNNING)
