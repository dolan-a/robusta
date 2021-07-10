import json
import logging
from typing import List, Optional
from threading import Lock

import kubernetes
from hikaru.model import ObjectMeta

from ...core.schedule.model import JobState
from ...integrations.kubernetes.autogenerated.v1.models import ConfigMap
from ...runner.not_found_exception import NotFoundException

CONFIGMAP_NAME = "jobs-states"
CONFIGMAP_NAMESPACE = "robusta"
mutex = Lock()


def load_config_map() -> ConfigMap:
    return ConfigMap.readNamespacedConfigMap(CONFIGMAP_NAME, CONFIGMAP_NAMESPACE).obj


def init_scheduler_dal():
    try:
        load_config_map()
    except kubernetes.client.exceptions.ApiException as e:
        # we only want to catch exceptions because the config map doesn't exist
        if e.reason != "Not Found":
            raise
        # job states configmap doesn't exists, create it
        mutex.acquire()
        try:
            conf_map = ConfigMap(
                metadata=ObjectMeta(name=CONFIGMAP_NAME, namespace=CONFIGMAP_NAMESPACE)
            )
            conf_map.createNamespacedConfigMap(conf_map.metadata.namespace)
            logging.info(
                f"created jobs states configmap {CONFIGMAP_NAME} {CONFIGMAP_NAMESPACE}"
            )
        finally:
            mutex.release()


init_scheduler_dal()


def save_scheduled_job_state(job_state: JobState):
    mutex.acquire()
    try:
        confMap = load_config_map()
        confMap.data[job_state.params.playbook_id] = job_state.json()
        confMap.replaceNamespacedConfigMap(
            confMap.metadata.name, confMap.metadata.namespace
        )
    finally:
        mutex.release()


def get_scheduled_job_state(playbook_id: str) -> Optional[JobState]:
    state_data = load_config_map().data.get(playbook_id)
    return JobState(**json.loads(state_data)) if state_data is not None else None


def del_scheduled_job_state(playbook_id: str):
    mutex.acquire()
    try:
        confMap = load_config_map()
        if confMap.data.get(playbook_id) is not None:
            del confMap.data[playbook_id]
            confMap.replaceNamespacedConfigMap(
                confMap.metadata.name, confMap.metadata.namespace
            )
    finally:
        mutex.release()


def list_scheduled_jobs_states() -> List[JobState]:
    return [get_scheduled_job_state(pid) for pid in load_config_map().data.keys()]
