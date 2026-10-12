from celery import shared_task
from django.utils import timezone
from .models import LogisticsLedger, MROExtractionJob
from .services.mro_ocr import extract_mro_document_data

@shared_task
def compute_variance_task(ledger_id):
    try:
        ledger = LogisticsLedger.objects.get(id=ledger_id)
        # Avoid triggering the custom save method again that re-dispatches the task
        # so we calculate it here and use update() to save.
        ledger._compute_variance()
        LogisticsLedger.objects.filter(id=ledger_id).update(
            variance_percent=ledger.variance_percent,
            variance_exceeds_tolerance=ledger.variance_exceeds_tolerance
        )
        return f"Variance computed for ledger {ledger_id}: {ledger.variance_percent}%"
    except LogisticsLedger.DoesNotExist:
        return f"Ledger {ledger_id} not found."


@shared_task
def process_mro_ocr_task(job_id):
    """
    Asynchronous Celery worker task that processes uploaded MRO files using
    AWS Textract (with fallback support) and updates MROExtractionJob state.
    """
    try:
        job = MROExtractionJob.objects.select_related("cluster").get(id=job_id)
        job.status = MROExtractionJob.Status.PROCESSING
        job.save(update_fields=["status"])

        file_bytes = b""
        if job.document:
            try:
                job.document.open("rb")
                file_bytes = job.document.read()
                job.document.close()
            except Exception as read_err:
                job.status = MROExtractionJob.Status.FAILED
                job.error_message = f"Error reading document: {read_err}"
                job.save(update_fields=["status", "error_message"])
                return f"Failed to read document for job {job_id}"

        extracted = extract_mro_document_data(
            file_bytes=file_bytes,
            file_name=job.file_name or job.document.name,
            cluster=job.cluster,
        )

        job.status = MROExtractionJob.Status.COMPLETED
        job.extracted_data = extracted
        job.average_confidence = extracted.get("average_confidence", 0.85)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "extracted_data", "average_confidence", "completed_at"])
        return f"MRO OCR Extraction complete for job {job_id}"

    except MROExtractionJob.DoesNotExist:
        return f"MROExtractionJob {job_id} not found."
    except Exception as exc:
        try:
            job = MROExtractionJob.objects.get(id=job_id)
            job.status = MROExtractionJob.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=["status", "error_message"])
        except Exception:
            pass
        return f"MRO OCR Extraction failed for job {job_id}: {exc}"
