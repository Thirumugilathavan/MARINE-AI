"""
Provider Registry for the Unified Marine Data Architecture.

Maintains singleton registrations of all marine data providers
(Copernicus, NOAA, Argo, INCOIS) and provides unified catalogue
search, dataset lookup, and provider dispatching.
"""

import logging
from typing import Dict, List, Optional

from app.modules.data_sources.base import (
    BaseMarineProvider,
    ProviderMetadata,
    ProviderDatasetMeta,
)
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
)
from app.modules.data_sources.copernicus_adapter import CopernicusMarineProvider
from app.modules.data_sources.noaa.service import NOAAMarineProvider
from app.modules.data_sources.argo.service import ArgoMarineProvider
from app.modules.data_sources.incois.service import INCOISMarineProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for marine data providers.
    """

    def __init__(self):
        self._providers: Dict[str, BaseMarineProvider] = {}
        self._initialize_default_providers()

    def _initialize_default_providers(self) -> None:
        """Register the 4 core marine data providers."""
        try:
            self.register(CopernicusMarineProvider())
        except Exception as exc:
            logger.warning(f"Could not register Copernicus provider: {exc}")

        try:
            self.register(NOAAMarineProvider())
        except Exception as exc:
            logger.warning(f"Could not register NOAA provider: {exc}")

        try:
            self.register(ArgoMarineProvider())
        except Exception as exc:
            logger.warning(f"Could not register Argo provider: {exc}")

        try:
            self.register(INCOISMarineProvider())
        except Exception as exc:
            logger.warning(f"Could not register INCOIS provider: {exc}")

    def register(self, provider: BaseMarineProvider) -> None:
        """Registers a provider instance."""
        meta = provider.metadata()
        pid = meta.provider_id.lower()
        self._providers[pid] = provider
        logger.info(f"Registered marine provider: {meta.name} ({pid})")

    def get(self, provider_id: str) -> BaseMarineProvider:
        """Returns the provider matching provider_id."""
        pid = provider_id.lower()
        if pid not in self._providers:
            raise ValueError(
                f"Unknown marine provider '{provider_id}'. "
                f"Registered providers: {list(self._providers.keys())}"
            )
        return self._providers[pid]

    def list_providers(self) -> List[ProviderMetadata]:
        """Returns metadata for all registered providers."""
        return [p.metadata() for p in self._providers.values()]

    def list_datasets(self, provider_id: Optional[str] = None) -> List[ProviderDatasetMeta]:
        """Lists registered datasets, optionally filtered by provider."""
        if provider_id:
            return self.get(provider_id).list_datasets()
        
        all_datasets: List[ProviderDatasetMeta] = []
        for p in self._providers.values():
            all_datasets.extend(p.list_datasets())
        return all_datasets

    def get_dataset(self, dataset_id: str, provider_id: Optional[str] = None) -> ProviderDatasetMeta:
        """Retrieves metadata for a specific dataset ID across all or one provider."""
        if provider_id:
            return self.get(provider_id).get_dataset(dataset_id)

        for p in self._providers.values():
            try:
                return p.get_dataset(dataset_id)
            except DatasetNotFoundError:
                continue

        raise DatasetNotFoundError(
            f"Dataset '{dataset_id}' not found in any registered provider catalogue."
        )

    def search_catalogue(
        self,
        query: str,
        provider_id: Optional[str] = None,
        variables: Optional[List[str]] = None,
        data_type: Optional[str] = None,
    ) -> List[ProviderDatasetMeta]:
        """Searches across provider catalogues."""
        if provider_id:
            return self.get(provider_id).search_catalogue(query, variables=variables, data_type=data_type)

        results: List[ProviderDatasetMeta] = []
        for p in self._providers.values():
            results.extend(p.search_catalogue(query, variables=variables, data_type=data_type))
        return results


# Global singleton instance
provider_registry = ProviderRegistry()
