from __future__ import annotations

from django.conf import settings


class OCRService:
    def analyze_page(self, file_path: str) -> dict:
        return self._azure_analyze(file_path)

    def _azure_analyze(self, file_path: str) -> dict:
        if not settings.AZURE_DI_ENDPOINT or not settings.AZURE_DI_KEY:
            raise RuntimeError(
                "Azure Document Intelligence credentials missing. "
                "Set AZURE_DI_ENDPOINT and AZURE_DI_KEY."
            )

        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=settings.AZURE_DI_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_DI_KEY),
        )
        with open(file_path, "rb") as f:
            poller = client.begin_analyze_document("prebuilt-read", f)
        return poller.result().as_dict()

    def _local_gpu_analyze(self, file_path: str) -> dict:
        raise NotImplementedError
