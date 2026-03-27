from __future__ import annotations

from typing import Iterable


def _docker_client():
    try:
        import docker
    except Exception as e:
        raise RuntimeError("docker SDK is required for container deployments") from e
    return docker.from_env()


def ensure_network(network_name: str = "model_network"):
    client = _docker_client()
    networks = client.networks.list(names=[network_name])
    if networks:
        return networks[0]
    return client.networks.create(network_name, driver="bridge")


def build_image(deployment_id: str, build_context_path: str, image_name: str | None = None) -> tuple[str, str]:
    client = _docker_client()
    tag = image_name or f"model-deployment:{deployment_id}"

    image, logs = client.images.build(path=build_context_path, tag=tag, rm=True)

    collected = []
    if isinstance(logs, Iterable):
        for item in logs:
            if isinstance(item, dict) and item.get("stream"):
                collected.append(item["stream"])

    return image.tags[0] if image.tags else tag, "".join(collected).strip()


def run_container(
    image_name: str,
    deployment_id: str,
    network_name: str = "model_network",
    internal_port: int = 5000,
    mem_limit: str = "512m",
    nano_cpus: int = 500_000_000,
):
    client = _docker_client()
    ensure_network(network_name)

    container_name = f"model_{deployment_id}"

    try:
        stale = client.containers.get(container_name)
        stale.remove(force=True)
    except Exception:
        pass

    container = client.containers.run(
        image_name,
        detach=True,
        name=container_name,
        network=network_name,
        mem_limit=mem_limit,
        nano_cpus=nano_cpus,
        user="1000:1000",
        environment={"PORT": str(internal_port)},
    )
    return container


def stop_container(container_name: str):
    client = _docker_client()
    container = client.containers.get(container_name)
    container.stop(timeout=10)


def delete_container(container_name: str):
    client = _docker_client()
    container = client.containers.get(container_name)
    container.remove(force=True)


def get_container_status(container_name: str) -> str:
    client = _docker_client()
    container = client.containers.get(container_name)
    container.reload()
    return container.status
