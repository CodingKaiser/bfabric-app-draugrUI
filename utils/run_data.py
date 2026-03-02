"""
Domain-specific data fetching for Run entities from B-Fabric.

Extracts lane/container/server information that the generic framework
entity_data() does not provide.
"""

from utils.bfabric_utils import get_logger, get_user_wrapper


def fetch_run_entity_data(token_data: dict) -> dict | None:
    """
    Fetch run-specific entity data from B-Fabric: lanes, containers, server, datafolder.

    This replicates the custom logic from the old auth_utils.entity_data() that
    traverses run → rununit → rununitlane → sample → container.

    Args:
        token_data: Validated token data dict from process_url_and_token().

    Returns:
        Dict with keys: name, createdby, created, modified, lanes, containers, server, datafolder.
        Returns None on failure.
    """
    entity_class_map = {
        "Run": "run",
        "Sample": "sample",
        "Project": "container",
        "Order": "container",
        "Container": "container",
        "Plate": "plate",
    }

    entity_class = token_data.get('entityClass_data')
    endpoint = entity_class_map.get(entity_class)
    entity_id = token_data.get('entity_id_data')

    if not endpoint or not entity_id:
        return None

    L = get_logger(token_data)
    wrapper = get_user_wrapper(token_data)

    # Fetch the main entity (Run)
    entity_data_list = L.logthis(
        api_call=wrapper.read,
        endpoint=endpoint,
        obj={"id": entity_id},
        max_results=None,
        flush_logs=False,
    )

    if not entity_data_list:
        L.flush_logs()
        return None

    entity_data_dict = entity_data_list[0]

    # Traverse run → rununit → rununitlane → samples → containers
    rununit_id = entity_data_dict.get("rununit", {}).get("id")
    if not rununit_id:
        L.flush_logs()
        return None

    lane_data_list = L.logthis(
        api_call=wrapper.read,
        endpoint="rununit",
        obj={"id": str(rununit_id)},
        max_results=None,
        flush_logs=False,
    )

    if not lane_data_list:
        L.flush_logs()
        return None

    lane_data = lane_data_list[0]

    lane_samples = L.logthis(
        api_call=wrapper.read,
        endpoint="rununitlane",
        obj={"id": [str(elt["id"]) for elt in lane_data.get("rununitlane", [])]},
        max_results=None,
        flush_logs=False,
    )

    sample_lanes = {}
    for lane in lane_samples:
        sample_ids = [str(elt["id"]) for elt in lane.get("sample", [])]

        if not sample_ids:
            samples = []
        elif len(sample_ids) < 100:
            samples = L.logthis(
                api_call=wrapper.read,
                endpoint="sample",
                obj={"id": sample_ids},
                max_results=None,
                flush_logs=False,
            )
        else:
            samples = []
            for i in range(0, len(sample_ids), 100):
                samples += L.logthis(
                    api_call=wrapper.read,
                    endpoint="sample",
                    obj={"id": sample_ids[i:i + 100]},
                    max_results=None,
                    flush_logs=False,
                )

        container_ids = list(set([
            sample.get("container", {}).get("id")
            for sample in samples
            if sample.get("container")
        ]))

        sample_lanes[str(lane.get("position"))] = [
            f"{cid} {L.logthis(api_call=wrapper.read, endpoint='container', obj={'id': str(cid)}, max_results=None, flush_logs=False)[0].get('name', '')}"
            for cid in container_ids
        ]

    L.flush_logs()

    return {
        "name": entity_data_dict.get("name", ""),
        "createdby": entity_data_dict.get("createdby", ""),
        "created": entity_data_dict.get("created", ""),
        "modified": entity_data_dict.get("modified", ""),
        "lanes": sample_lanes,
        "containers": [
            container["id"]
            for container in entity_data_dict.get("container", [])
            if container.get("classname") == "order"
        ],
        "server": entity_data_dict.get("serverlocation", ""),
        "datafolder": entity_data_dict.get("datafolder", ""),
    }
