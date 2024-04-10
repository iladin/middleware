from typing import List

from dora.service.incidents.integration import get_incidents_integration_service
from dora.service.incidents.sync.etl_incidents_factory import IncidentsETLFactory
from dora.service.incidents.sync.etl_provider_handler import IncidentsProviderETLHandler
from dora.store.models.incidents import (
    OrgIncidentService,
    IncidentBookmarkType,
    IncidentProvider,
    IncidentsBookmark,
)
from dora.store.repos.incidents import IncidentsRepoService
from dora.utils.log import LOG
from dora.utils.time import time_now


class IncidentsETLHandler:
    def __init__(
        self,
        provider: IncidentProvider,
        incident_repo_service: IncidentsRepoService,
        etl_service: IncidentsProviderETLHandler,
    ):
        self.provider = provider
        self.incident_repo_service = incident_repo_service
        self.etl_service = etl_service

    def sync_org_incident_services(self, org_id: str):
        try:
            incident_services = self.incident_repo_service.get_org_incident_services(
                org_id
            )
            updated_services = self.etl_service.get_updated_incident_services(
                incident_services
            )
            self.incident_repo_service.update_org_incident_services(
                org_id, updated_services
            )
            for service in updated_services:
                try:
                    self._sync_service_incidents(service)
                except Exception as e:
                    LOG.error(
                        f"Error syncing incidents for service {service.key}: {str(e)}"
                    )
                    continue
        except Exception as e:
            LOG.error(f"Error syncing incident services for org {org_id}: {str(e)}")
            return

    def _sync_service_incidents(self, service: OrgIncidentService):
        try:
            bookmark = self.__get_incidents_bookmark(service)
            (
                incidents,
                incident_org_incident_service_map,
                bookmark,
            ) = self.etl_service.process_service_incidents(service, bookmark)
            self.incident_repo_service.save_incidents_data(
                incidents, incident_org_incident_service_map
            )
            self.incident_repo_service.save_incidents_bookmark(bookmark)

        except Exception as e:
            LOG.error(f"Error syncing incidents for service {service.key}: {str(e)}")
            return

    def __get_incidents_bookmark(self, service: OrgIncidentService):
        bookmark = self.incident_repo_service.get_incidents_bookmark(
            str(service.id), IncidentBookmarkType.SERVICE, self.provider
        )
        if not bookmark:
            bookmark = IncidentsBookmark(
                entity_id=str(service.id),
                entity_type=IncidentBookmarkType.SERVICE,
                provider=self.provider.value,
                bookmark=time_now(),
            )
        return bookmark


def sync_org_incidents(org_id: str):
    incident_providers: List[
        str
    ] = get_incidents_integration_service().get_org_providers(org_id)
    etl_factory = IncidentsETLFactory(org_id)

    for provider in incident_providers:
        try:
            incident_provider = IncidentProvider(provider)
            incidents_etl_handler = IncidentsETLHandler(
                incident_provider, IncidentsRepoService(), etl_factory(provider)
            )
            incidents_etl_handler.sync_org_incident_services(org_id)
        except Exception as e:
            LOG.error(
                f"Error syncing incidents for provider {provider}, org {org_id}: {str(e)}"
            )
            continue
    LOG.info(f"Synced incidents for org {org_id}")
