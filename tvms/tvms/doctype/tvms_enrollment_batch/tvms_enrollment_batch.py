# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TVMSEnrollmentBatch(Document):
    """Audit row for every CSV import. Created at the start of an import
    and updated as the import progresses. The status field is the source
    of truth: IN PROGRESS → COMPLETED / FAILED / PARTIAL.
    """
    pass