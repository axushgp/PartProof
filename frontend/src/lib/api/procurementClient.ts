import {
  DecisionReplayRequest,
  DecisionReplayResult,
  ExtractedDocument,
  ProcurementAuditPayload,
  SupplierComparisonResult,
} from "@/types/procurement";
import { TaskDetail } from "@/types/backend";

export class ProcurementApiError extends Error {
  status: number;
  constructor(message: string, status: number = 500) {
    super(message);
    this.name = "ProcurementApiError";
    this.status = status;
  }
}

export async function fetchProcurementDemo(): Promise<ProcurementAuditPayload> {
  const res = await fetch("/api/procurement/demo", { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to load demo case" }));
    throw new ProcurementApiError(err.detail || "Failed to load demo case", res.status);
  }
  return res.json();
}

export async function extractDocuments(
  bomFile: File | null,
  quoteFiles: File[],
  supplierNames?: string[]
): Promise<ExtractedDocument[]> {
  const formData = new FormData();
  if (bomFile) {
    formData.append("bom_file", bomFile);
  }
  for (const q of quoteFiles) {
    formData.append("quote_files", q);
  }
  if (supplierNames && supplierNames.length > 0) {
    formData.append("supplier_names", supplierNames.join(","));
  }

  const res = await fetch("/api/procurement/extract", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Extraction failed" }));
    throw new ProcurementApiError(err.detail || "Extraction failed", res.status);
  }
  return res.json();
}

export async function reconcileProcurement(
  payload: ProcurementAuditPayload
): Promise<SupplierComparisonResult> {
  const res = await fetch("/api/procurement/reconcile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Reconciliation failed" }));
    throw new ProcurementApiError(err.detail || "Reconciliation failed", res.status);
  }
  return res.json();
}

export async function replayDecision(
  auditPayload: ProcurementAuditPayload,
  replayRequest: DecisionReplayRequest
): Promise<DecisionReplayResult> {
  const res = await fetch("/api/procurement/replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audit_payload: auditPayload, replay_request: replayRequest }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Decision replay failed" }));
    throw new ProcurementApiError(err.detail || "Decision replay failed", res.status);
  }
  return res.json();
}

export async function createProcurementTask(
  payload: ProcurementAuditPayload
): Promise<TaskDetail> {
  const res = await fetch("/api/procurement/create-task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Task creation failed" }));
    throw new ProcurementApiError(err.detail || "Task creation failed", res.status);
  }
  return res.json();
}
